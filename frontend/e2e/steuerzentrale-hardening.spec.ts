import { expect, test } from '@playwright/test';

const apiBase = '**/api/**';
test.use({ timezoneId: 'America/Los_Angeles' });

async function installAdmin(page: any) {
  await page.addInitScript(() => {
    localStorage.setItem('access', 'test-access');
    localStorage.setItem('refresh', 'test-refresh');
  });
}

function operationsOverview() {
  return {
    role: 'admin',
    notifications: [{ id: 'n1', title: 'Berlin-Zeitprüfung', body: 'Zeitstempel muss in Deutschland angezeigt werden.', created_at: '2026-01-01T23:30:00Z', read_at: null }],
    readiness: { google_login: true, apple_login: true, email_delivery: true, company_legal_data: true, aueg_data: true, final_contract_set_complete: true, android_signing_configured: true, ios_signing_configured: true, store_api_credentials_configured: true, contract_templates: {} },
    conflicts: [], unavailable_assignments: [], coverage_gaps: [], overtime_risks: [], pending_swaps: 2, unapproved_time_entries: 3, contracts_due_30: 4, estimated_monthly_labor_cost: '1234.50',
  };
}

function catalog() {
  return { count: 8, complete: true, recovery: { complete: true, expected: 8, installed: 8, recovered: 0, missing: [], ambiguous: [], invalid: [] }, documents: Array.from({ length: 8 }, (_, index) => ({ slug: `d${index}`, name: `Dokument ${index + 1}`, version: '1.0', source_format: 'docx', source_installed: true, signature_roles: ['employee'] })) };
}

async function fulfillCommon(route: any, degradedWorkingTime = false) {
  const url = new URL(route.request().url());
  const path = `${url.pathname}${url.search}`;
  if (url.pathname.endsWith('/auth/me/')) return route.fulfill({ json: { id: 'admin', role: 'admin', first_name: 'Admin', last_name: '', name: 'Admin', email: 'admin@example.com', phone: '' } });
  if (url.pathname.endsWith('/dashboard/')) return route.fulfill({ json: { workers: 1, clients: 1, open_shifts: 0, pending_time_off: 0, contracts_due: 0, upcoming_shifts: [] } });
  if (url.pathname.endsWith('/operations/')) return route.fulfill({ json: operationsOverview() });
  if (url.pathname.endsWith('/operations/folders/')) return route.fulfill({ json: { workers: [], clients: [] } });
  if (url.pathname.endsWith('/integrations/wiw/status/')) return route.fulfill({ json: { configured: false, migration_only: true, latest_sync: null } });
  if (url.pathname.endsWith('/document-catalog/')) return route.fulfill({ json: catalog() });
  if (url.pathname.endsWith('/automation/orders/packages/')) return route.fulfill({ json: { results: [] } });
  if (url.pathname.endsWith('/working-time/settings/')) { if (degradedWorkingTime) return route.fulfill({ status: 503, json: { detail: 'temporary outage' } }); return route.fulfill({ json: { employees: [] } }); }
  if (url.pathname.endsWith('/working-time/records/')) return route.fulfill({ json: { results: [] } });
  if (url.pathname.endsWith('/auth/saml/status/')) return route.fulfill({ json: { enabled: false } });
  if (url.pathname.endsWith('/premium/scheduling-policy/')) return route.fulfill({ json: { auto_schedule_enabled: true, pickup_approval_required: false, labor_sharing_enabled: true, allow_overlapping_open_shifts: false, allow_multiple_shifts_per_day: false, timezone_toggle_enabled: true, min_hours_between_days: 11, max_hours_per_day: 10, max_hours_per_week: 48, max_days_in_row: 6 } });
  if (url.pathname.includes('/premium/')) return route.fulfill({ json: { results: [] } });
  if (url.pathname.endsWith('/locations/')) return route.fulfill({ json: { results: [] } });
  if (url.pathname.endsWith('/shifts/') && url.searchParams.get('status') === 'draft') return route.fulfill({ json: { results: [] } });
  if (url.pathname.includes('/workers/') || url.pathname.includes('/clients/') || url.pathname.includes('/positions/')) return route.fulfill({ json: { results: [] } });
  return route.fulfill({ json: { results: [], path } });
}

async function openOperations(page: any) {
  await page.goto('/');
  await page.getByText('Anfragen, Berichte & Verwaltung', { exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Anfragen, Berichte & Verwaltung' })).toBeVisible();
}

async function expectWorkforceProControlsVisible(page: any) {
  const premium = page.getByTestId('premium-operations-panel');
  await expect(premium).toBeVisible();
  const labels = ['Automatische Dienstplanung','OpenShift-Übernahme freigeben','Standortübergreifender Personaleinsatz','Überlappende OpenShifts zulassen','Mehrere Schichten pro Tag','Zeitzonenumschaltung'];
  for (const label of labels) {
    const node = premium.getByText(label, { exact: true }).last();
    await expect(node).toBeVisible();
    const style = await node.evaluate((element) => { const computed = getComputedStyle(element); return { visibility: computed.visibility, opacity: computed.opacity, color: computed.color }; });
    expect(style.visibility).toBe('visible'); expect(Number(style.opacity)).toBeGreaterThan(0); expect(style.color).not.toBe('rgba(0, 0, 0, 0)'); expect(style.color).not.toBe('rgb(255, 255, 255)');
  }
  await expect(premium.getByRole('switch')).toHaveCount(6);
  for (let index = 0; index < 6; index += 1) await expect(premium.getByRole('switch').nth(index)).toBeVisible();
  await expect(premium.getByRole('spinbutton', { name: 'Ruhezeit zwischen Tagen' })).toHaveValue('11');
  await expect(premium.getByRole('spinbutton', { name: 'Maximale Stunden pro Tag' })).toHaveValue('10');
  await expect(premium.getByRole('spinbutton', { name: 'Maximale Stunden pro Woche' })).toHaveValue('48');
  await expect(premium.getByRole('spinbutton', { name: 'Maximale Tage in Folge' })).toHaveValue('6');
  await expect(premium.getByText('Regeln speichern', { exact: true })).toBeVisible();
  await expect(premium.getByText('Vorschau', { exact: true })).toBeVisible();
  await expect(premium.getByText('Automatisch besetzen', { exact: true })).toBeVisible();
}

test('KPI cards stay visible and German timestamps use Europe/Berlin', async ({ page }) => {
  await installAdmin(page); await page.route(apiBase, (route) => fulfillCommon(route)); await openOperations(page);
  const cards = page.locator('.operations-stats ion-card');
  await expect(cards).toHaveCount(5); await expect(cards.nth(0)).toContainText('Planungsrisiken'); await expect(cards.nth(0)).toContainText('0'); await expect(cards.nth(1)).toContainText('Offene Tauschanfragen'); await expect(cards.nth(1)).toContainText('2'); await expect(cards.nth(2)).toContainText('Ungeprüfte Zeiten'); await expect(cards.nth(2)).toContainText('3'); await expect(cards.nth(3)).toContainText('Verträge ≤ 30 Tage'); await expect(cards.nth(3)).toContainText('4'); await expect(cards.nth(4)).toContainText('Geplante Lohnkosten'); await expect(cards.nth(4)).toContainText(/1[.\s]234,50\s*€/);
  for (let index = 0; index < 5; index += 1) { const content = cards.nth(index).locator('ion-card-content'); await expect(content).toBeVisible(); const style = await content.evaluate((element) => { const computed = getComputedStyle(element); return { visibility: computed.visibility, opacity: computed.opacity, color: computed.color }; }); expect(style.visibility).toBe('visible'); expect(Number(style.opacity)).toBeGreaterThan(0); expect(style.color).not.toBe('rgba(0, 0, 0, 0)'); }
  await expect(page.getByText(/2\.1\.2026.*00:30/)).toBeVisible(); await expect(page.getByText('8/8 installiert')).toBeVisible(); await expectWorkforceProControlsVisible(page);
});

test('one auxiliary 503 no longer breaks the whole operations center', async ({ page }) => {
  await installAdmin(page); await page.route(apiBase, (route) => fulfillCommon(route, true)); await openOperations(page);
  await expect(page.getByTestId('working-time-panel')).toBeVisible(); await expect(page.getByText('Arbeitszeitkonto', { exact: true })).toBeVisible(); await expect(page.getByText('Ein Teil der Daten ist vorübergehend nicht erreichbar.')).toBeVisible(); await expect(page.getByText(/Arbeitszeitkonto: neutraler Fallback wird angezeigt/)).toBeVisible(); await expect(page.getByText('8/8 installiert')).toBeVisible(); await expectWorkforceProControlsVisible(page);
});
