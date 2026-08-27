import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

test('attendance uses Berlin business time independent of device timezone', async () => {
  const source = readFileSync(resolve(process.cwd(), 'src/AttendanceV3.tsx'), 'utf8');
  expect(source).toContain("const BUSINESS_TIME_ZONE = 'Europe/Berlin'");
  expect(source).toContain('timeZone: BUSINESS_TIME_ZONE');
  expect(source).not.toContain('getTimezoneOffset()');
});

test('imported WIW attendance stays visible but read-only in employee history', async () => {
  const source = readFileSync(resolve(process.cwd(), 'src/AttendanceV3.tsx'), 'utf8');
  expect(source).toContain('entry.wiw_time_id ?');
  expect(source).toContain('WIW-Historie · schreibgeschützt');
  expect(source).toContain('pendingByEntry.has(entry.id)');
});
