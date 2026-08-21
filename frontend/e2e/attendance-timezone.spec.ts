import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

test('attendance uses Berlin business time independent of device timezone', async () => {
  const source = readFileSync(resolve(process.cwd(), 'src/AttendanceV3.tsx'), 'utf8');
  expect(source).toContain("const BUSINESS_TIME_ZONE = 'Europe/Berlin'");
  expect(source).toContain('timeZone: BUSINESS_TIME_ZONE');
  expect(source).not.toContain('getTimezoneOffset()');
});
