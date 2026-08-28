import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

// Phase 7 completion acceptance contract. This comment intentionally keeps the
// latest CI run attributable to the repository owner rather than the Actions bot.
const read = (file:string) => readFileSync(resolve(process.cwd(), file), 'utf8');

test('completion sweep keeps one editable datetime field, automatic pause and capacity controls', async () => {
  const schedule = read('src/ScheduleV2.tsx');
  expect(schedule).toContain('type="datetime-local"');
  expect(schedule).toContain('Datum & Uhrzeit');
  expect(schedule).toContain('automaticBreakMinutes');
  expect(schedule).toContain('ab 6h: 30');
  expect(schedule).toContain('ab 9h: 45');
  expect(schedule).toContain('ab 11h: 60');
  expect(schedule).toContain('data-testid="required-count-stepper"');
  expect(schedule).toContain('Maximal ${limit} Mitarbeiter auswählbar.');
  expect(schedule).not.toContain('label="Pause (Min.)"');
});

test('completion sweep scopes locations, activates inline map creation and supports note templates', async () => {
  const schedule = read('src/ScheduleV2.tsx');
  const main = read('src/main.tsx');
  const settings = read('src/Settings.tsx');
  expect(schedule).toContain('locations.filter(x=>form.client&&x.client===form.client)');
  expect(schedule).toContain('Einsatzort anlegen');
  expect(schedule).toContain('enrichLocationPayload');
  expect(schedule).toContain('NOTE_TEMPLATES');
  expect(schedule).toContain('Textvorlage für Mitarbeiterhinweis');
  expect(main).toContain('installLocationPicker();');
  expect(settings).toContain("path==='locations/'?await enrichLocationPayload(payload):payload");
});

test('completion sweep stores Zeitplan and per-worker OpenShift client visibility', async () => {
  const schedule = read('src/ScheduleV2.tsx');
  const akte = read('src/AktePage.tsx');
  expect(schedule).toContain('Zeitplan · Sichtbare Mitarbeitergruppen');
  expect(schedule).toContain("/hotel\\s*spenerhaus/i");
  expect(schedule).toContain("['front_office','housekeeping']");
  expect(akte).toContain('OpenShifts sichtbar für Kunden');
  expect(akte).toContain('Zeitplan-Gruppen');
  expect(akte).toContain('open_shift_client_ids');
  expect(akte).toContain('schedule_groups');
});
