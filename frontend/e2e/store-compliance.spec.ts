import { expect, test } from '@playwright/test';

test('login clearly identifies the app as internal and exposes legal links', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText('Interner Unternehmenszugang')).toBeVisible();
  await expect(page.getByText(/Keine öffentliche Registrierung/)).toBeVisible();
  await expect(page.getByRole('link', { name: 'Datenschutz' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Kontolöschung' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Support' })).toBeVisible();
});

test('privacy policy is public and store-ready', async ({ page }) => {
  await page.goto('/datenschutz');
  await expect(page.getByRole('heading', { name: 'Datenschutzinformation für die A+ Solution App' })).toBeVisible();
  await expect(page.getByText(/keine öffentliche Selbstregistrierung/i)).toBeVisible();
  await expect(page.getByText(/keine Hintergrundortung/i)).toBeVisible();
  await expect(page.getByText(/§ 26 BDSG/)).toBeVisible();
  await expect(page.getByText(/Die rechtlich finale Fassung wird vor Store-Veröffentlichung/i)).toHaveCount(0);
});

test('deletion, imprint and support pages are public', async ({ page }) => {
  await page.goto('/konto-loeschen');
  await expect(page.getByRole('heading', { name: 'Kontolöschung und Datenlöschung' })).toBeVisible();
  await expect(page.getByText(/Mein Profil/)).toBeVisible();

  await page.goto('/impressum');
  await expect(page.getByRole('heading', { name: 'Impressum' })).toBeVisible();
  await expect(page.getByText('A+ Solution GmbH', { exact: true })).toBeVisible();
  await expect(page.getByText(/HRB 128570/)).toBeVisible();

  await page.goto('/support');
  await expect(page.getByRole('heading', { name: 'Support für die A+ Solution App' })).toBeVisible();
  await expect(page.getByText(/keine öffentliche Registrierung/i)).toBeVisible();
});
