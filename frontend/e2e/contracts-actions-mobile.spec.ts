import { expect, Page, Route, test } from '@playwright/test';

async function fulfill(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

const baseReadiness = {
  state: 'ready_to_send',
  blocking_issues: [],
  generation_allowed: true,
  send_allowed: true,
  pending_signature_roles: [] as string[],
  completed_signature_roles: [] as string[],
  document_current: true,
};

async function mockAdmin(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('access', 'contract-actions-access');
    localStorage.setItem('refresh', 'contract-actions-refresh');
  });

  const contracts = [
    {
      id: 'blocked-1', title: 'QA Blocked PDF', template_name: 'Aufhebungsvertrag', status: 'draft',
      starts_on: '2026-08-21', ends_on: '2035-12-31', signatures: [], pdf: null,
      readiness: { ...baseReadiness, state: 'blocked', generation_allowed: false, send_allowed: false, blocking_issues: [{ code: 'required_data_missing', label: 'Pflichtangaben fehlen.' }] },
    },
    {
      id: 'employee-only-1', title: 'QA Employee Only', template_name: 'Merkblatt', status: 'ready',
      starts_on: '2026-08-21', ends_on: '2030-01-01', signatures: [], pdf: '/media/contracts/employee-only.pdf',
      readiness: { ...baseReadiness, pending_signature_roles: ['employee'] },
    },
    {
      id: 'employer-1', title: 'QA Employer Sign', template_name: 'Arbeitsvertrag', status: 'ready',
      starts_on: '2026-08-21', ends_on: '2030-01-01', signatures: [], pdf: '/media/contracts/employer.pdf',
      readiness: { ...baseReadiness, pending_signature_roles: ['employer'] },
    },
  ];
  let signPayload: any;

  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api\//, '');
    if (path === 'auth/me/') return fulfill(route, {
      id: 'admin-1', email: 'admin@example.test', name: 'A+ Admin', first_name: 'A+', last_name: 'Admin', role: 'admin', phone: '',
    });
    if (path.startsWith('contracts/employer-1/sign/') && request.method() === 'POST') {
      signPayload = request.postDataJSON();
      return fulfill(route, {
        ...contracts[2], status: 'signed', signatures: [{ id: 'sig-1', role: 'employer', signer_name: signPayload.name }],
        readiness: { ...baseReadiness, generation_allowed: false, send_allowed: false, pending_signature_roles: [], completed_signature_roles: ['employer'] },
      });
    }
    if (path.startsWith('contracts/')) return fulfill(route, contracts);
    if (path === 'contract-templates/') return fulfill(route, [{
      id: 'template-1', name: 'QA Vertrag', version: '1', active: true,
      schema: { fields: [] },
    }]);
    if (path.startsWith('workers/')) return fulfill(route, [{ id: 'worker-1', active: true, user_detail: { name: 'QA Worker' } }]);
    if (path.startsWith('clients/')) return fulfill(route, [{ id: 'client-1', active: true, name: 'QA Client GmbH' }]);
    if (path === 'document-center/') return fulfill(route, { summary: {}, actions: [], templates: [], contracts: [] });
    if (path === 'health/' || path === 'readiness/') return fulfill(route, { ok: true });
    return fulfill(route, []);
  });

  return { getSignPayload: () => signPayload };
}

test('contract actions follow backend readiness and drawing signature sends PNG data', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const state = await mockAdmin(page);
  await page.goto('/?view=contracts');

  const blocked = page.locator('.contract-row').filter({ hasText: 'QA Blocked PDF' });
  await expect(blocked.getByRole('button', { name: 'PDF nicht bereit' })).toBeVisible();
  await expect(blocked.getByRole('button', { name: 'PDF erstellen' })).toHaveCount(0);
  await expect(blocked.getByRole('button', { name: /Versenden/ })).toHaveCount(0);

  const employeeOnly = page.locator('.contract-row').filter({ hasText: 'QA Employee Only' });
  await expect(employeeOnly.getByRole('button', { name: 'Als Arbeitgeber unterschreiben' })).toHaveCount(0);

  const employer = page.locator('.contract-row').filter({ hasText: 'QA Employer Sign' });
  await employer.getByRole('button', { name: 'Als Arbeitgeber unterschreiben' }).click();
  await expect(page.getByRole('heading', { name: 'Vertrag unterzeichnen' })).toBeVisible();
  await page.getByLabel('Vollständiger Name').fill('QA Arbeitgeber');

  const canvas = page.getByLabel('Unterschrift zeichnen');
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  expect(box).not.toBeNull();
  if (!box) return;
  await page.mouse.move(box.x + 35, box.y + 70);
  await page.mouse.down();
  await page.mouse.move(box.x + 110, box.y + 50, { steps: 5 });
  await page.mouse.move(box.x + 190, box.y + 95, { steps: 5 });
  await page.mouse.up();
  await page.getByRole('button', { name: 'Verbindlich unterzeichnen' }).click();

  await expect.poll(() => state.getSignPayload()).toBeTruthy();
  const payload = state.getSignPayload();
  expect(payload.name).toBe('QA Arbeitgeber');
  expect(String(payload.signature)).toMatch(/^data:image\/png;base64,/);
});

test('contract date picker explicitly supports years beyond 2027', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockAdmin(page);
  await page.goto('/?view=contracts');
  await page.getByRole('button', { name: 'Neuer Vertrag' }).click();

  const endDate = page.locator('ion-input[label="Vertragsende"]');
  await expect(endDate).toBeVisible();
  await endDate.click();

  const picker = page.locator('ion-modal.friendly-picker-modal');
  await expect(picker).toBeVisible();
  const datetime = picker.locator('ion-datetime[presentation="date"]');
  await expect(datetime).toHaveAttribute('max', '2100-12-31');
  await expect(datetime).toHaveAttribute('min', '1900-01-01');

  await datetime.evaluate((element: any) => {
    element.value = '2035-12-31';
    element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: '2035-12-31' }, bubbles: true, composed: true }));
  });
  await picker.getByRole('button', { name: 'Übernehmen' }).click();
  await expect.poll(async () => endDate.evaluate((element: any) => String(element.value || ''))).toBe('2035-12-31');
});
