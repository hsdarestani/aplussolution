import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const source = (path: string) => readFileSync(resolve(process.cwd(), path), 'utf8');

test('mobile app renders at device width without pinch or double-tap zoom', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');

  const viewport = page.locator('meta[name="viewport"]');
  await expect(viewport).toHaveAttribute('content', /width=device-width/);
  await expect(viewport).toHaveAttribute('content', /initial-scale=1/);
  await expect(viewport).toHaveAttribute('content', /maximum-scale=1/);
  await expect(viewport).toHaveAttribute('content', /user-scalable=no/);
  await expect(page.locator('html')).toHaveCSS('touch-action', 'pan-x pan-y');
});

test('publisher iOS build disables native WKWebView pinch zoom', () => {
  const preparer = source('scripts/prepare-native.mjs');
  const iosPublisher = source('scripts/build-publisher-ios.sh');
  expect(preparer).toContain('webView?.scrollView.pinchGestureRecognizer?.isEnabled = false');
  expect(iosPublisher).toContain('node scripts/prepare-native.mjs ios');
});
