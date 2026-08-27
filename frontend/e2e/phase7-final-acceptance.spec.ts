import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const source = (path: string) => readFileSync(resolve(process.cwd(), path), 'utf8');

test('Phase 7 keeps the final Mitteilungen contract and removes active Chat UX', async () => {
  const app = source('src/App.tsx');
  expect(app).toContain("['messages', 'Mitteilungen']");
  expect(app).toContain('function Announcements');
  expect(app).toContain("api('announcements/')");
  expect(app).toContain('data-testid="announcements-view"');
  expect(app).toContain('data-testid="announcement-create"');
  expect(app).toContain('Posteingang');
  expect(app).toContain('Versandhistorie');
  expect(app).not.toContain("api('conversations/')");
  expect(app).not.toContain('portal/message-recipients/');
  expect(app).not.toContain('Neue Unterhaltung');
  expect(app).not.toContain("['messages', 'Nachrichten']");
});

test('Phase 7 keeps confirmation, immutable WIW history and digital-file navigation together', async () => {
  const schedule = source('src/ScheduleV2.tsx');
  const attendance = source('src/AttendanceV3.tsx');
  const app = source('src/App.tsx');
  const search = source('src/GlobalSearch.tsx');

  expect(schedule).toContain('confirmation_required');
  expect(schedule).toContain("'Ausstehend'");
  expect(schedule).toContain("'Bestätigt'");
  expect(schedule).toContain("'Abgelehnt'");
  expect(schedule).toContain('confirmation/');

  expect(attendance).toContain('WIW-Historie · schreibgeschützt');
  expect(app).toContain('data-testid="people-kind-filter"');
  expect(app).toContain("akteHref('worker', worker.id)");
  expect(app).toContain("akteHref('client', client.id)");
  expect(search).toContain('openAkte(result.type, result.id)');
});

test('Phase 7 preserves the Phase 5 shift-card information order', async () => {
  const schedule = source('src/ScheduleV2.tsx');
  const fields = ['client', 'location', 'workers', 'time', 'profile'];
  const positions = fields.map((field) => schedule.indexOf(`data-field="${field}"`));
  positions.forEach((position) => expect(position).toBeGreaterThan(-1));
  for (let index = 1; index < positions.length; index += 1) {
    expect(positions[index - 1]).toBeLessThan(positions[index]);
  }
  expect(schedule).toContain('{renderShiftDetails(x)}');
  expect(schedule).toContain('renderShiftDetails(item,compact)');
});
