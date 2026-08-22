import { expect, test } from '@playwright/test';

test.use({ timezoneId: 'America/Los_Angeles', locale: 'en-US' });

test('Workforce Pro keeps German planning dates while APIs receive ISO dates', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('access', 'test-access');
    localStorage.setItem('refresh', 'test-refresh');
  });

  let autoPayload: any = null;
  await page.route('**/api/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (path.endsWith('/auth/me/')) return route.fulfill({ json: { id: 'admin', role: 'admin', first_name: 'Admin', last_name: '', name: 'Admin', email: 'admin@example.com', phone: '' } });
    if (path.endsWith('/dashboard/')) return route.fulfill({ json: { workers: 0, clients: 0, open_shifts: 0, pending_time_off: 0, contracts_due: 0, upcoming_shifts: [] } });
    if (path.endsWith('/operations/')) return route.fulfill({ json: { role: 'admin', notifications: [], readiness: { final_contract_set_complete: true, contract_templates: {} }, conflicts: [], unavailable_assignments: [], coverage_gaps: [], overtime_risks: [], swaps: [], swap_candidates: [], pending_swaps: 0, unapproved_time_entries: 0, contracts_due_30: 0, estimated_monthly_labor_cost: '0' } });
    if (path.endsWith('/operations/folders/')) return route.fulfill({ json: { workers: [], clients: [] } });
    if (path.endsWith('/integrations/wiw/status/')) return route.fulfill({ json: { configured: false, migration_only: true, latest_sync: null } });
    if (path.endsWith('/document-catalog/')) return route.fulfill({ json: { count: 8, complete: true, documents: Array.from({ length: 8 }, (_, index) => ({ slug: `d${index}`, name: `Dokument ${index + 1}`, version: '1.0', source_format: 'docx', source_installed: true, signature_roles: [] })) } });
    if (path.endsWith('/automation/orders/packages/')) return route.fulfill({ json: { results: [] } });
    if (path.endsWith('/working-time/settings/')) return route.fulfill({ json: { employees: [] } });
    if (path.endsWith('/working-time/records/')) return route.fulfill({ json: { results: [] } });
    if (path.endsWith('/auth/saml/status/')) return route.fulfill({ json: { enabled: false } });
    if (path.endsWith('/premium/scheduling-policy/')) return route.fulfill({ json: { auto_schedule_enabled: true, pickup_approval_required: false, labor_sharing_enabled: true, allow_overlapping_open_shifts: true, allow_multiple_shifts_per_day: false, timezone_toggle_enabled: true, min_hours_between_days: 11, max_hours_per_day: 10, max_hours_per_week: 48, max_days_in_row: 6 } });
    if (path.endsWith('/premium/auto-schedule/') && request.method() === 'POST') {
      autoPayload = request.postDataJSON();
      return route.fulfill({ json: { assigned: 0, unfilled: 0 } });
    }
    if (path.includes('/premium/')) return route.fulfill({ json: { results: [] } });
    if (path.endsWith('/locations/')) return route.fulfill({ json: { results: [] } });
    if (path.endsWith('/shifts/') && url.searchParams.get('status') === 'draft') return route.fulfill({ json: { results: [] } });
    if (path.includes('/workers/') || path.includes('/clients/') || path.includes('/positions/')) return route.fulfill({ json: { results: [] } });
    return route.fulfill({ json: { results: [] } });
  });

  await page.goto('/');
  await page.getByText('Anfragen, Berichte & Verwaltung', { exact: true }).click();
  const premium = page.getByTestId('premium-operations-panel');
  await expect(premium).toBeVisible();

  const from = premium.getByRole('textbox', { name: 'Von' });
  const until = premium.getByRole('textbox', { name: 'Bis' });
  await expect(from).toHaveAttribute('placeholder', 'TT.MM.JJJJ');
  await expect(until).toHaveAttribute('placeholder', 'TT.MM.JJJJ');
  await expect(from).toHaveValue(/^\d{2}\.\d{2}\.\d{4}$/);
  await expect(until).toHaveValue(/^\d{2}\.\d{2}\.\d{4}$/);

  await from.fill('31.12.2026');
  await from.press('Enter');
  await until.fill('02.01.2027');
  await until.press('Enter');
  await premium.getByText('Vorschau', { exact: true }).click();

  await expect.poll(() => autoPayload).not.toBeNull();
  expect(autoPayload.start).toBe('2026-12-31');
  expect(autoPayload.end).toBe('2027-01-02');
});
