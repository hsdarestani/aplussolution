import { expect, Page, Route, test } from '@playwright/test';

const client = {
  id: 'client-user-qa',
  email: 'qa.client.portal@example.test',
  name: 'QA Claudia Kunde',
  first_name: 'QA Claudia',
  last_name: 'Kunde',
  role: 'client',
  phone: '',
};

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function mockClientApi(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('access', 'client-location-e2e');
    localStorage.setItem('refresh', 'client-location-refresh');
  });

  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api\//, '');

    if (path === 'auth/me/') return json(route, client);
    if (path === 'dashboard/') return json(route, { active_orders: 0, upcoming_shifts: 0, contracts_to_sign: 0 });
    if (path.startsWith('orders/')) return json(route, []);
    if (path === 'locations/') {
      return json(route, [
        {
          id: 'location-own',
          name: 'QA Client Portal Standort',
          client: 'client-own',
          client_name: 'QA Client Portal GmbH',
          address: 'Musterstraße 10, 60329 Frankfurt am Main',
          active: true,
        },
      ]);
    }
    return json(route, []);
  });
}

test('client order form loads only the client-scoped locations returned by the API', async ({ page }) => {
  await mockClientApi(page);
  await page.goto('/');

  await page.getByText('Aufträge', { exact: true }).first().click();
  await expect(page.getByRole('heading', { name: 'Aufträge' })).toBeVisible();
  await page.getByRole('button', { name: 'Neuer Auftrag' }).click();

  const locationSelect = page.locator('ion-select').filter({ hasText: 'Einsatzort' }).last();
  await locationSelect.click();

  await expect(page.getByText('QA Client Portal Standort', { exact: true })).toBeVisible();
  await expect(page.getByText('QA Frankfurt Testsite', { exact: true })).toHaveCount(0);
});
