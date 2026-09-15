import { expect, Page, Route, test } from '@playwright/test';

const client = {
  id: 'client-v2-user',
  email: 'kunde.v2@example.test',
  name: 'Claudia Kunde',
  first_name: 'Claudia',
  last_name: 'Kunde',
  role: 'client',
  phone: '',
};

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function mockClient(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('access', 'client-v2-access');
    localStorage.setItem('refresh', 'client-v2-refresh');
  });
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api\//, '');
    if (path === 'auth/me/') return json(route, client);
    if (path === 'portal/client-dashboard/') return json(route, { role: 'client', active_orders: 2, upcoming_shifts: 1, contracts_to_sign: 1 });
    if (path === 'operations/folders/') return json(route, { workers: [], clients: [{ id: 'company-v2', name: 'Kunde V2 GmbH', customer_number: 'KD-V2', documents: 1, contracts: 1, orders: 2 }] });
    if (path === 'operations/') return json(route, { role: 'client', unread_notifications: 2, open_orders: 2, notifications: [] });
    if (path.startsWith('orders/')) return json(route, [
      { id: 'order-v2', title: 'Abendveranstaltung', client: 'company-v2', client_name: 'Kunde V2 GmbH', location: 'loc-v2', location_name: 'Frankfurt Mitte', requested_staff: 4, starts_at: '2026-09-20T16:00:00Z', ends_at: '2026-09-20T22:00:00Z', status: 'planning' },
    ]);
    if (path.startsWith('shifts/')) return json(route, [
      { id: 'shift-v2', client: 'company-v2', client_name: 'Kunde V2 GmbH', location_name: 'Frankfurt Mitte', position_name: 'Servicekraft', starts_at: '2026-09-20T16:00:00Z', ends_at: '2026-09-20T22:00:00Z', status: 'confirmed' },
    ]);
    if (path.startsWith('contracts/')) return json(route, [
      { id: 'contract-v2', title: 'Rahmenvertrag', client: 'company-v2', client_name: 'Kunde V2 GmbH', status: 'sent', signatures: [], readiness: { pending_signature_roles: ['client'] }, updated_at: '2026-09-15T08:00:00Z' },
    ]);
    if (path.startsWith('documents/')) return json(route, [
      { id: 'doc-v2', title: 'Einsatzinformation', client: 'company-v2', client_name: 'Kunde V2 GmbH', folder: 'orders', visibility: 'client', file: '/media/doc-v2.pdf', created_at: '2026-09-15T08:00:00Z' },
    ]);
    if (path === 'payroll/') return json(route, []);
    if (path === 'locations/') return json(route, [{ id: 'loc-v2', name: 'Frankfurt Mitte', client: 'company-v2', client_name: 'Kunde V2 GmbH', address: 'Frankfurt', active: true }]);
    if (path === 'portal/rating-candidates/') return json(route, []);
    if (path.startsWith('ratings/')) return json(route, []);
    if (path.startsWith('announcements/')) return json(route, []);
    return json(route, []);
  });
}

test('client gets a dedicated A+ dashboard with scoped live actions', async ({ page }) => {
  await mockClient(page);
  await page.goto('/');

  const home = page.getByTestId('client-portal-v2-home');
  await expect(home).toBeVisible();
  await expect(home.getByRole('heading', { name: 'Guten Tag, Claudia' })).toBeVisible();
  await expect(home.getByText(/Kunde V2 GmbH/).first()).toBeVisible();
  await expect(home.getByText('Aktive Aufträge')).toBeVisible();
  await expect(home.getByText('Kommende Einsätze')).toBeVisible();
  await expect(home.getByText('Zu unterzeichnen')).toBeVisible();
  await expect(home.getByText('Servicekraft')).toBeVisible();
  await expect(home.getByText('Einsatzinformation')).toBeVisible();
  await expect(home.getByText(/Fremd|Andere GmbH/i)).toHaveCount(0);
});

test.describe('client v2 mobile navigation', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('keeps five customer-first destinations and a clean More screen', async ({ page }) => {
    await mockClient(page);
    await page.goto('/');

    const tabs = page.getByTestId('client-v2-tabbar');
    await expect(tabs).toBeVisible();
    await expect(tabs.getByRole('button', { name: 'Start' })).toBeVisible();
    await expect(tabs.getByRole('button', { name: 'Einsätze' })).toBeVisible();
    await expect(tabs.getByRole('button', { name: 'Aufträge' })).toBeVisible();
    await expect(tabs.getByRole('button', { name: 'Dokumente' })).toBeVisible();
    await expect(tabs.getByRole('button', { name: 'Weitere Bereiche öffnen' })).toBeVisible();

    await tabs.getByRole('button', { name: 'Aufträge' }).click();
    await expect(page.getByRole('heading', { name: 'Aufträge' })).toBeVisible();
    await expect(page.getByText('Abendveranstaltung')).toBeVisible();

    await tabs.getByRole('button', { name: 'Weitere Bereiche öffnen' }).click();
    const more = page.getByTestId('client-v2-more');
    await expect(more).toBeVisible();
    await expect(more.getByText('Verträge & Signatur')).toBeVisible();
    await expect(more.getByText('Servicecenter')).toBeVisible();
    await expect(more.getByText('Mitarbeiter bewerten')).toBeVisible();
    await expect(more.getByText('Mitteilungen')).toBeVisible();
    await expect(more.getByText('Profil & Sicherheit')).toBeVisible();
    await expect(more.getByText('Meine Stunden')).toHaveCount(0);

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });
});
