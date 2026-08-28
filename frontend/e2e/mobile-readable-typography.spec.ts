import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const source = (path: string) => readFileSync(resolve(process.cwd(), path), 'utf8');

test('mobile typography keeps admin and employee text readable', async () => {
  const css = source('src/mobile-readable-typography.css');
  const main = source('src/main.tsx');

  expect(main).toContain("import './mobile-readable-typography.css';");
  expect(css).toContain('--app-mobile-font-base: 15px');
  expect(css).toContain('.mobile-tabbar button span { font-size: 11px !important');
  expect(css).toContain('.wiw-mobile-row strong { font-size: 15px !important');
  expect(css).toContain('.wiw-more-row span { font-size: 15px !important');
  expect(css).toContain('.wiw-period-row strong { font-size: 14px !important');
  expect(css).toContain('.sv2-event-head strong { font-size: 15px !important');
  expect(css).toContain('.wiw-employee-detail-row { font-size: 16px !important');
  expect(css).toContain('ion-input,');
  expect(css).toContain('font-size: 16px !important;');
});
