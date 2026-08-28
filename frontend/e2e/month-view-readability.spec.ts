import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const source = (path: string) => readFileSync(resolve(process.cwd(), path), 'utf8');

test('month cards use icons without repeated field labels and keep readable values', async () => {
  const css = source('src/schedule-month-compact.css');
  const main = source('src/main.tsx');
  const schedule = source('src/ScheduleV2.tsx');

  expect(main).toContain("import './schedule-month-compact.css';");
  expect(css).toContain('.sv2 .sv2-month-grid .sv2-event-details.compact .sv2-field-copy>small{display:none}');
  expect(css).toContain('font-size:10px');
  expect(css).toContain('grid-template-columns:repeat(7,minmax(145px,1fr))');
  expect(schedule).toContain("view==='month'");
  expect(schedule).toContain('renderMini(item,true)');
});
