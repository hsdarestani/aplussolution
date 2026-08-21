import { expect, test } from '@playwright/test';

const apiBase = '**/api/**';

async function installAuth(page: any, role: 'admin' | 'client') {
  await page.addInitScript(({ role }) => {
    localStorage.setItem('access', 'test-access');
    localStorage.setItem('refresh', 'test-refresh');
    (window as any).__TEST_ROLE__ = role;
  }, { role });
}

test('admin can open a worker digital file', async ({ page }) => {
  await installAuth(page, 'admin');
  await page.route(apiBase, async (route) => {
    const url = route.request().url();
    if (url.endsWith('/auth/me/')) return route.fulfill({ json: { id: 'admin', role: 'admin', first_name: 'Admin', name: 'Admin', email: 'admin@example.com' } });
    if (url.includes('/workers/?')) return route.fulfill({ json: { results: [{ id: 'w1', employee_number: 'MA-001', active: true, ranking_points: 0, user_detail: { name: 'Anna Becker', email: 'anna@example.com' } }] } });
    if (url.includes('/clients/?')) return route.fulfill({ json: { results: [] } });
    if (url.endsWith('/workers/w1/akte/')) return route.fulfill({ json: { kind: 'worker', title: 'Anna Becker', number: 'MA-001', summary: { contracts: 1, documents: 1, payroll: 1, shifts: 0 }, contracts: [{ id: 'c1', title: 'Arbeitsvertrag', template_name: 'AV', status: 'signed', updated_at: '2026-08-21', pdf: '/media/av.pdf' }], document_folders: [{ key: 'certificates', label: 'Nachweise', count: 1, items: [{ id: 'd1', title: 'Ausweis', created_at: '2026-08-21', visibility: 'worker', file: '/media/id.pdf' }] }], payroll: [{ id: 'p1', period: '2026-08-01', document: '/media/payroll.pdf' }], shifts: [] } });
    if (url.includes('/dashboard/')) return route.fulfill({ json: { workers: 1, clients: 0, open_shifts: 0, pending_time_off: 0, contracts_due: 0, upcoming_shifts: [] } });
    if (url.includes('/locations/') || url.includes('/positions/')) return route.fulfill({ json: { results: [] } });
    return route.fulfill({ json: { results: [] } });
  });

  await page.goto('/');
  await page.getByText('Personal & Kunden', { exact: true }).click();
  await expect(page.getByText('Anna Becker')).toBeVisible();
  await page.getByRole('button', { name: 'Akte' }).click();
  await expect(page.getByTestId('akte-modal')).toBeVisible();
  await expect(page.getByText('Arbeitsvertrag')).toBeVisible();
  await expect(page.getByText('Nachweise')).toBeVisible();
});

test('client can upload a function sheet to an order', async ({ page }) => {
  await installAuth(page, 'client');
  let patched = false;
  await page.route(apiBase, async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    if (url.endsWith('/auth/me/')) return route.fulfill({ json: { id: 'client', role: 'client', first_name: 'Klara', name: 'Klara', email: 'client@example.com' } });
    if (url.includes('/dashboard/')) return route.fulfill({ json: { active_orders: 1, upcoming_shifts: 0, contracts_to_sign: 0 } });
    if (url.includes('/orders/?')) return route.fulfill({ json: { results: [{ id: 'o1', title: 'Sommerfest', starts_at: '2026-09-01T18:00:00Z', ends_at: '2026-09-01T23:00:00Z', requested_staff: 4, description: '', status: 'new', client_name: 'Kunde GmbH' }] } });
    if (url.endsWith('/orders/o1/') && method === 'PATCH') {
      patched = true;
      return route.fulfill({ json: { id: 'o1', title: 'Sommerfest', attachment: '/media/functions.pdf' } });
    }
    if (url.includes('/locations/')) return route.fulfill({ json: { results: [] } });
    return route.fulfill({ json: { results: [] } });
  });

  await page.goto('/');
  await page.getByText('Aufträge', { exact: true }).click();
  await page.getByTestId('order-upload-open').click();
  await page.getByTestId('order-file-input').setInputFiles({ name: 'functions.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4') });
  await page.getByLabel('Functions und Hinweise').fill('4 Service, 2 Runner');
  await page.getByRole('button', { name: 'Datei hochladen' }).click();
  await expect(page.getByText('Auftragsdatei wurde hochgeladen und dem Auftrag zugeordnet.')).toBeVisible();
  expect(patched).toBeTruthy();
});

test('contract sign modal exposes the real drawing pad and keeps PDF download action', async ({ page }) => {
  await installAuth(page, 'client');
  await page.route(apiBase, async (route) => {
    const url = route.request().url();
    if (url.endsWith('/auth/me/')) return route.fulfill({ json: { id: 'client', role: 'client', first_name: 'Klara', name: 'Klara', email: 'client@example.com' } });
    if (url.includes('/dashboard/')) return route.fulfill({ json: { active_orders: 0, upcoming_shifts: 0, contracts_to_sign: 1 } });
    if (url.includes('/contracts/?')) return route.fulfill({ json: { results: [{ id: 'c1', title: 'ANÜ Sommerfest', template_name: 'Einzelarbeitnehmerüberlassungsvertrag', status: 'sent', client_name: 'Kunde GmbH', pdf: '/media/anue.pdf', signatures: [], readiness: { state: 'awaiting_signature', generation_allowed: false, send_allowed: false, document_current: true, blocking_issues: [], completed_signature_roles: [], pending_signature_roles: ['client'] } }] } });
    return route.fulfill({ json: { results: [] } });
  });

  await page.goto('/');
  await page.getByText('Verträge & Signatur', { exact: true }).click();
  await expect(page.getByRole('link', { name: 'PDF' })).toHaveAttribute('href', '/media/anue.pdf');
  await page.getByRole('button', { name: 'Unterschreiben' }).click();
  await expect(page.getByLabel('Unterschrift zeichnen')).toBeVisible();
});
