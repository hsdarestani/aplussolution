import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

test('Phase 5 uses the exact shared shift-card information order in every calendar view', async () => {
  const source = readFileSync(resolve(process.cwd(), 'src/ScheduleV2.tsx'), 'utf8');
  const client = source.indexOf('data-field="client"');
  const location = source.indexOf('data-field="location"');
  const workers = source.indexOf('data-field="workers"');
  const time = source.indexOf('data-field="time"');
  const profile = source.indexOf('data-field="profile"');
  expect(client).toBeGreaterThan(-1);
  expect(client).toBeLessThan(location);
  expect(location).toBeLessThan(workers);
  expect(workers).toBeLessThan(time);
  expect(time).toBeLessThan(profile);
  expect(source).toContain('{renderShiftDetails(x)}');
  expect(source).toContain('renderShiftDetails(item,compact)');
  expect(source).toContain("openAkte('client'");
  expect(source).toContain("openAkte('worker'");
});

test('Phase 5 separates Mitarbeiter and Kunden folders and names open digital files', async () => {
  const app = readFileSync(resolve(process.cwd(), 'src/App.tsx'), 'utf8');
  const search = readFileSync(resolve(process.cwd(), 'src/GlobalSearch.tsx'), 'utf8');
  const akte = readFileSync(resolve(process.cwd(), 'src/AktePage.tsx'), 'utf8');
  expect(app).toContain('data-testid="people-kind-filter"');
  expect(app).toContain("peopleKind === 'workers'");
  expect(app).toContain("peopleKind === 'clients'");
  expect(app).toContain("akteHref('worker', worker.id)");
  expect(app).toContain("akteHref('client', client.id)");
  expect(search).toContain("result.type === 'worker' || result.type === 'client'");
  expect(search).toContain('openAkte(result.type, result.id)');
  expect(akte).toContain("url.searchParams.set('people_kind', kind === 'client' ? 'clients' : 'workers')");
});
