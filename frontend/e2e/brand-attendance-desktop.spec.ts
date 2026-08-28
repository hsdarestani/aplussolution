import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const read = (path: string) => readFileSync(resolve(process.cwd(), path), 'utf8');

test('A+ brand navy is the final color authority', async () => {
  const main = read('src/main.tsx');
  const css = read('src/brand-navy.css');
  expect(main).toContain("import './brand-navy.css';");
  expect(main.indexOf("import './brand-navy.css';")).toBeGreaterThan(main.indexOf("import './wiw-mobile-light.css';"));
  expect(css).toContain('--aplus-blue: #06283f');
  expect(css).toContain('--ion-color-primary: #06283f');
  expect(css).toContain('--wiw-primary: #06283f');
});

test('desktop attendance exposes synced history instead of exception-only emptiness', async () => {
  const main = read('src/main.tsx');
  const enhancer = read('src/DesktopAttendanceHistoryEnhancer.tsx');
  expect(main).toContain('<DesktopAttendanceHistoryEnhancer />');
  expect(enhancer).toContain("api('attendance/history/')");
  expect(enhancer).toContain('Alle erfassten Zeiten');
  expect(enhancer).toContain('WIW-Historie');
  expect(enhancer).toContain("window.matchMedia('(min-width: 901px)').matches");
});
