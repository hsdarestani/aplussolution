import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

test('Phase 6 exposes per-assignee confirmation status and direct controls in schedule cards', async () => {
  const source = readFileSync(resolve(process.cwd(), 'src/ScheduleV2.tsx'), 'utf8');
  expect(source).toContain('confirmation_required');
  expect(source).toContain("'Ausstehend'");
  expect(source).toContain("'Bestätigt'");
  expect(source).toContain("'Abgelehnt'");
  expect(source).toContain('shift-confirmations');
  expect(source).toContain('Bestätigen');
  expect(source).toContain('Ablehnen');
  expect(source).toContain('confirmation/');
  expect(source).toContain('Bestätigung durch zugewiesene Mitarbeiter erforderlich');
});

test('Phase 6 replaces Chat UI with one-way Mitteilungen, file upload, audience selection and history', async () => {
  const app = readFileSync(resolve(process.cwd(), 'src/App.tsx'), 'utf8');
  expect(app).toContain('function Announcements');
  expect(app).toContain("api('announcements/')");
  expect(app).toContain('all_recipients');
  expect(app).toContain('recipient_ids');
  expect(app).toContain('Bild / Datei');
  expect(app).toContain('Versandhistorie');
  expect(app).toContain('Push wurde ausgelöst');
  expect(app).toContain('data-testid="announcements-view"');
  expect(app).toContain('data-testid="announcement-create"');
  expect(app).not.toContain("api('conversations/')");
  expect(app).not.toContain('portal/message-recipients/');
  expect(app).not.toContain('Neue Unterhaltung');
  expect(app).not.toContain("messages: 'Chat'");
});
