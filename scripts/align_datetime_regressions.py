from pathlib import Path


def replace_once(path, old, new):
    p=Path(path); text=p.read_text(encoding='utf-8')
    if old not in text: raise SystemExit(f'missing expected block in {path}')
    p.write_text(text.replace(old,new,1),encoding='utf-8')

replace_once(
    'frontend/e2e/contracts-actions-mobile.spec.ts',
    """  await datetime.evaluate((element: any) => {
    element.value = '2035-12-31';
    element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: '2035-12-31' }, bubbles: true, composed: true }));
  });
  await picker.getByRole('button', { name: 'Übernehmen' }).click();
  await expect.poll(async () => endDate.evaluate((element: any) => String(element.value || ''))).toBe('2035-12-31');
""",
    """  await datetime.evaluate((element: any) => {
    element.value = '2035-12-31';
    element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: '2035-12-31' }, bubbles: true, composed: true }));
  });
  await expect(picker).not.toBeVisible();
  await expect.poll(async () => endDate.evaluate((element: any) => String(element.value || ''))).toBe('2035-12-31');
""",
)

replace_once(
    'frontend/e2e/worker-portal-deep.spec.ts',
    """async function setFriendlyDateTime(page: Page, label: string, next: string) {
  const field = page.locator(`ion-input[label=\"${label}\"]`);
  await field.click();
  const picker = page.locator('ion-modal.friendly-picker-modal');
  await expect(picker).toBeVisible();
  const datetime = picker.locator('ion-datetime[presentation=\"date-time\"]');
  await datetime.evaluate((element: any, value) => {
    element.value = value;
    element.dispatchEvent(new CustomEvent('ionChange', { detail: { value }, bubbles: true, composed: true }));
  }, next);
  await picker.getByRole('button', { name: 'Übernehmen' }).click();
  await expect(picker).not.toBeVisible();
  await expect.poll(async () => field.evaluate((element: any) => String(element.value || ''))).toBe(next);
}
""",
    """async function setEditableDateTime(page: Page, label: string, next: string) {
  const field = page.locator(`ion-input[label=\"${label}\"]`);
  await expect(field).toBeVisible();
  await expect(field).not.toHaveAttribute('readonly', '');
  await field.evaluate((element: any, value) => {
    element.value = value;
    element.dispatchEvent(new CustomEvent('ionInput', { detail: { value }, bubbles: true, composed: true }));
    element.dispatchEvent(new CustomEvent('ionChange', { detail: { value }, bubbles: true, composed: true }));
  }, next);
  await expect.poll(async () => field.evaluate((element: any) => String(element.value || ''))).toBe(next);
}
""",
)
replace_once(
    'frontend/e2e/worker-portal-deep.spec.ts',
    "  test('availability and notifications work through the friendly picker', async ({ page }) => {",
    "  test('availability uses directly editable date-time fields and notifications remain worker-scoped', async ({ page }) => {",
)
replace_once(
    'frontend/e2e/worker-portal-deep.spec.ts',
    "    await setFriendlyDateTime(page, 'Beginn', '2026-08-24T09:00');\n    await setFriendlyDateTime(page, 'Ende', '2026-08-24T18:00');",
    "    await setEditableDateTime(page, 'Beginn', '2026-08-24T09:00');\n    await setEditableDateTime(page, 'Ende', '2026-08-24T18:00');",
)
