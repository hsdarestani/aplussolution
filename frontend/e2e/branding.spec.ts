import { expect, test } from '@playwright/test';

test.describe('A+ Solution branding', () => {
  test('serves the supplied company logo and uses it on the login screen', async ({ page, request }) => {
    const asset = await request.get('/5.png');
    expect(asset.ok()).toBeTruthy();
    expect(asset.headers()['content-type']).toContain('image/png');

    await page.goto('/');
    const brand = page.locator('.brand .logo');
    await expect(brand).toBeVisible();
    const background = await brand.evaluate((element) => getComputedStyle(element).backgroundImage);
    expect(background).toContain('/5.png');
  });
});
