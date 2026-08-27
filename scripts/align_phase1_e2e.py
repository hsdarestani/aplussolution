from pathlib import Path


def replace_once(path, old, new, label):
    p=Path(path); text=p.read_text(); count=text.count(old)
    if count!=1: raise SystemExit(f'{label}: expected 1 match, found {count}')
    p.write_text(text.replace(old,new,1))

replace_once(
    'frontend/e2e/app-shell.spec.ts',
    "      'Personal & Kunden',\n      'Aufträge & AI',\n      'Verträge & ANÜ',",
    "      'Personal & Kunden',\n      'Einstellungen',\n      'Verträge & ANÜ',",
    'admin nav expectation',
)

replace_once(
    'frontend/e2e/friendly-datetime.spec.ts',
    "  await page.getByRole('button', { name: 'Personalbedarf' }).click();",
    "  await page.getByTestId('schedule-create-manual').click();",
    'manual schedule button expectation',
)

p=Path('frontend/e2e/masterdata-quick.spec.ts')
text=p.read_text()
start=text.index("test('master data quick access")
new_test="""test('settings owns locations and positions after Personal & Kunden cleanup', async ({ page }) => {\n  await page.setViewportSize({ width: 390, height: 844 });\n  await mockApi(page);\n  await page.goto('/?view=settings');\n\n  await expect(page.getByRole('heading', { name: 'Einstellungen' })).toBeVisible();\n  await expect(page.getByText('QA Newest Testsite', { exact: true })).toBeVisible();\n  await expect(page.getByText('QA Newest Position', { exact: true })).toBeVisible();\n  await expect(page.getByText('Standort 1', { exact: true })).toBeVisible();\n\n  await page.getByRole('button', { name: 'Position', exact: true }).click();\n  await expect(page.getByRole('heading', { name: 'Position anlegen' })).toBeVisible();\n  await expect(page.locator('ion-input[type=\"color\"]')).toBeVisible();\n});\n"""
p.write_text(text[:start]+new_test)
