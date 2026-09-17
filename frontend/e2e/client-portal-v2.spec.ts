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

const access = {
  client_id: 'company-v2',
  client_name: 'Kunde V2 GmbH',
  account_name: 'Claudia Kunde',
  first_name: 'Claudia',
  read_only: false,
  location_scope_id: null,
  location_scope_name: '',
  capabilities: {},
};

const shift = {
  id: 'shift-v2',
  client: 'company-v2',
  client_name: 'Kunde V2 GmbH',
  location: 'loc-v2',
  location_name: 'Frankfurt Mitte',
  position_name: 'Servicekraft',
  starts_at: '2026-09-20T16:00:00Z',
  ends_at: '2026-09-20T22:00:00Z',
  status: 'confirmed',
  required_count: 2,
  filled_count: 2,
  notes: 'Abendservice im Saal',
  assigned_workers: [],
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
    if (path === 'portal/client-access/') return json(route, access);
    if (path === 'portal/client-shifts/') return json(route, [shift]);
    if (path === 'portal/client-documents/') return json(route, [
      {
        id: 'doc-v2',
        title: 'Einsatzinformation',
        file: '/media/doc-v2.pdf',
        uploaded_by_name: 'A+ Disposition',
        created_at: '2026-09-15T08:00:00Z',
      },
    ]);
    if (path === 'portal/client-order-metadata/') return json(route, {
      locations: [{ id: 'loc-v2', name: 'Frankfurt Mitte' }],
      positions: [{ id: 'position-service', name: 'Servicekraft' }],
    });
    if (path.startsWith('orders/')) return json(route, [
      { id: 'order-v2', title: 'Abendveranstaltung', client: 'company-v2', client_name: 'Kunde V2 GmbH', location: 'loc-v2', location_name: 'Frankfurt Mitte', requested_staff: 4, starts_at: '2026-09-20T16:00:00Z', ends_at: '2026-09-20T22:00:00Z', status: 'planning' },
    ]);
    if (path === 'portal/rating-candidates/') return json(route, []);
    if (path.startsWith('ratings/')) return json(route, []);
    if (path.startsWith('announcements/')) return json(route, []);
    return json(route, []);
  });
}

test('client gets the simplified dashboard with personal request and shared documents only', async ({ page }) => {
  await mockClient(page);
  await page.goto('/');

  const home = page.getByTestId('client-portal-v2-home');
  await expect(home).toBeVisible();
  await expect(home.getByRole('heading', { name: 'Guten Tag, Claudia' })).toBeVisible();
  await expect(home.getByText(/Kunde V2 GmbH/).first()).toBeVisible();
  await expect(home.getByRole('heading', { name: 'Personal genau dann, wenn du es brauchst.' })).toBeVisible();
  await expect(home.getByRole('button', { name: /Personal anfragen/ })).toBeVisible();
  await expect(home.getByRole('heading', { name: 'Gemeinsamer Ordner' })).toBeVisible();
  await expect(home.getByText('Einsatzinformation')).toBeVisible();
  await expect(home.getByText('Aktive Aufträge')).toHaveCount(0);
  await expect(home.getByText('Zu unterzeichnen')).toHaveCount(0);
  await expect(home.getByText('Was möchtest du erledigen?')).toHaveCount(0);
  await expect(home.getByText('AKTIONEN')).toHaveCount(0);
  await expect(home.getByText(/Fremd|Andere GmbH/i)).toHaveCount(0);
});

test.describe('client v4 mobile navigation', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('keeps four customer destinations and removes Servicecenter and Verträge from Mehr', async ({ page }) => {
    await mockClient(page);
    await page.goto('/');

    const tabs = page.getByTestId('client-v2-tabbar');
    await expect(tabs).toBeVisible();
    await expect(tabs.getByRole('button')).toHaveCount(4);
    await expect(tabs.getByRole('button', { name: 'Dashboard' })).toBeVisible();
    await expect(tabs.getByRole('button', { name: 'Kalender' })).toBeVisible();
    await expect(tabs.getByRole('button', { name: 'Bewerten' })).toBeVisible();
    await expect(tabs.getByRole('button', { name: 'Weitere Bereiche öffnen' })).toBeVisible();

    await tabs.getByRole('button', { name: 'Weitere Bereiche öffnen' }).click();
    const more = page.getByTestId('client-v2-more');
    await expect(more).toBeVisible();
    await expect(more.getByRole('button', { name: /Personal anfragen/ })).toBeVisible();
    await expect(more.getByRole('button', { name: /Dokumente/ })).toBeVisible();
    await expect(more.getByRole('button', { name: /Mitteilungen/ })).toBeVisible();
    await expect(more.getByRole('button', { name: /Profil & Sicherheit/ })).toBeVisible();
    await expect(more.getByRole('button', { name: /Verträge/ })).toHaveCount(0);
    await expect(more.getByRole('button', { name: /Servicecenter/ })).toHaveCount(0);

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });
});
