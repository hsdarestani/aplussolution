import { readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, Page, Route, test } from '@playwright/test';

const client = {
  id: 'client-visual-qa',
  email: 'visual.client@example.test',
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

function todayShift() {
  const start = new Date();
  start.setUTCHours(8, 30, 0, 0);
  const end = new Date(start.getTime() + 8.5 * 60 * 60 * 1000);
  return {
    id: 'shift-client-visual',
    client: 'client-own',
    client_name: 'Marthas',
    position: 'position-service',
    position_name: 'Servicekraft',
    location: 'location-own',
    location_name: 'Evangelische Akademie',
    starts_at: start.toISOString(),
    ends_at: end.toISOString(),
    break_minutes: 30,
    status: 'confirmed',
    required_count: 1,
    filled_count: 1,
    notes: 'Terrasse vorbereiten',
    assigned_workers: [{ id: 'worker-francesco', slot_id: 'slot-francesco', name: 'Francesco Trulli', is_me: false }],
  };
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function mockClient(page: Page, state: { ratingPost?: any }) {
  const shift = todayShift();
  await page.addInitScript(() => {
    localStorage.setItem('access', 'client-visual-token');
    localStorage.setItem('refresh', 'client-visual-refresh');
  });
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const pathName = url.pathname.replace(/^\/api\//, '');
    const method = route.request().method();
    if (pathName === 'auth/me/') return json(route, client);
    if (pathName === 'portal/client-access/') return json(route, access);
    if (pathName === 'portal/client-shifts/') return json(route, [shift]);
    if (pathName === 'portal/client-documents/') return json(route, []);
    if (pathName === 'portal/client-order-metadata/') return json(route, { locations: [], positions: [] });
    if (pathName.startsWith('orders/')) return json(route, []);
    if (pathName === 'portal/rating-candidates/') return json(route, [{
      shift_id: shift.id,
      worker_id: 'worker-francesco',
      worker_name: 'Francesco Trulli',
      location_name: shift.location_name,
      starts_at: shift.starts_at,
      ends_at: shift.ends_at,
      notes: shift.notes,
    }]);
    if (pathName.startsWith('ratings/')) {
      if (method === 'POST') {
        state.ratingPost = route.request().postDataJSON();
        return json(route, { id: 'rating-new', worker_name: 'Francesco Trulli', created_at: new Date().toISOString(), ...state.ratingPost }, 201);
      }
      return json(route, []);
    }
    return json(route, []);
  });
}

test.describe('client portal visual parity', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('client enhancers are session-keyed so a fresh login does not need a manual refresh', async () => {
    const source = readFileSync(path.join(process.cwd(), 'src/main.tsx'), 'utf8');
    expect(source).toContain('function ClientPortalMount()');
    expect(source).toContain("localStorage.getItem('access')");
    expect(source).toContain('window.setInterval(syncSession, 180)');
    expect(source).toContain('<React.Fragment key={generation}>');
    expect(source).toContain('<ClientPortalMount />');
  });

  test('calendar stays compact, scrollable and exposes notes in shift detail', async ({ page }) => {
    const state: { ratingPost?: any } = {};
    await mockClient(page, state);
    await page.goto('/');

    const tabs = page.getByTestId('client-v2-tabbar');
    await expect(tabs.getByRole('button')).toHaveCount(4);
    await tabs.getByRole('button', { name: 'Kalender' }).click();

    const calendar = page.locator('.client-v4-schedule');
    await expect(calendar).toBeVisible();
    await expect(calendar.locator('.client-v4-weekbar')).toBeVisible();
    await expect(calendar.getByRole('button', { name: /Evangelische Akademie.*Terrasse vorbereiten/ })).toBeVisible();
    await calendar.getByRole('button', { name: /Evangelische Akademie.*Terrasse vorbereiten/ }).click();

    const detail = page.locator('.client-v4-shift-detail');
    await expect(detail).toBeVisible();
    await expect(detail.getByText('Einsatzdetails')).toBeVisible();
    await expect(detail.getByText('Evangelische Akademie')).toBeVisible();
    await expect(detail.getByText('Francesco Trulli')).toBeVisible();
    await expect(detail.getByText('Terrasse vorbereiten', { exact: true })).toBeVisible();
    await expect(detail.getByRole('button', { name: /Zeit \/ Datum ändern/ })).toBeVisible();
    await expect(detail.getByRole('button', { name: /Stornierung anfragen/ })).toBeVisible();

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });

  test('rating screen is shift-first and submits one selected worker', async ({ page }) => {
    const state: { ratingPost?: any } = {};
    await mockClient(page, state);
    await page.goto('/');

    const tabs = page.getByTestId('client-v2-tabbar');
    await tabs.getByRole('button', { name: 'Bewerten' }).click();
    const ratings = page.locator('.client-v4-ratings');
    await expect(ratings).toBeVisible();
    await expect(ratings.getByRole('heading', { name: 'Einsatz auswählen' })).toBeVisible();
    await ratings.getByRole('button', { name: /Evangelische Akademie.*Terrasse vorbereiten/ }).click();
    await expect(ratings.getByRole('heading', { name: 'Einzeln bewerten' })).toBeVisible();
    await ratings.getByRole('button', { name: /Francesco Trulli/ }).click();

    const dialog = page.getByRole('dialog');
    const totalStars = dialog.locator('.client-v4-score').first().getByRole('button');
    await totalStars.nth(3).click();
    await dialog.locator('textarea').fill('Sehr guter Einsatz.');
    await dialog.getByRole('button', { name: 'Bewertung speichern' }).click();

    await expect.poll(() => state.ratingPost).toBeTruthy();
    expect(state.ratingPost.shift).toBe('shift-client-visual');
    expect(state.ratingPost.worker).toBe('worker-francesco');
    expect(state.ratingPost.score).toBe(4);
  });
});
