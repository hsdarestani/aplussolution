import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const schedulePath = path.resolve(here, '../src/WiwScheduleMobile.tsx');
let source = fs.readFileSync(schedulePath, 'utf8');
let changed = false;

// The native picker must be sourced from the live worker directory. Eligibility
// is already enforced by WiwWorkerPickerEligibilityEnhancer using schedule_groups;
// a second hard-coded name whitelist made valid/assigned workers such as Store
// Reviewer disappear from the picker entirely.
const hardcodedFilter = "\n    .filter((item: Choice) => allowedWorkerNames.has(normalize(item.label)))";
if (source.includes(hardcodedFilter)) {
  source = source.replace(hardcodedFilter, '');
  changed = true;
}

// An assigned/confirmed card is not an OpenShift. The old edit form reused
// `publish_now` for every non-draft shift and therefore displayed an enabled
// OpenShift switch even when a worker was already assigned. Show the actual
// direct assignment while a worker is selected; if the admin removes the worker,
// the OpenShift control becomes available again.
const oldOpenShiftRow = '          <Row icon={personOutline} label="OpenShift" value={form.publish_now ? \'Für passende Mitarbeiter sichtbar\' : \'Aus · ohne Zuweisung nur als Entwurf\'} trailing={<Switch checked={form.publish_now} onChange={(value) => setForm((current) => ({ ...current, publish_now: value }))} />} />';
const newOpenShiftRow = '          {editing && form.workers.length ? <Row icon={personOutline} label="Direkt zugewiesen" value={selectedWorkerNames || editing.workerName} emphasizeValue /> : <Row icon={personOutline} label="OpenShift" value={form.publish_now ? \'Für passende Mitarbeiter sichtbar\' : \'Aus · ohne Zuweisung nur als Entwurf\'} trailing={<Switch checked={form.publish_now} onChange={(value) => setForm((current) => ({ ...current, publish_now: value }))} />} />}';
if (source.includes(oldOpenShiftRow)) {
  source = source.replace(oldOpenShiftRow, newOpenShiftRow);
  changed = true;
} else if (!source.includes('label="Direkt zugewiesen"')) {
  throw new Error('Native schedule OpenShift edit row marker not found');
}

// Show the day's total scheduled staff-hours next to the shift-card count in the
// grey day header. The calculation mirrors Gesamtstunden and deducts breaks.
const oldDayHeader = '<header><span className="wiw-day-header-spacer"/><div className="wiw-day-heading"><strong>{header.weekday}</strong><span>{header.date}</span></div><em>{dayCards.length}</em></header>';
const newDayHeader = '<header><span className="wiw-day-header-spacer"/><div className="wiw-day-heading"><strong>{header.weekday}</strong><span>{header.date}</span></div><em>{dayCards.length}<small> · {dayCards.reduce((sum, card) => { const gross = Math.max(0, (new Date(card.shift.ends_at).getTime() - new Date(card.shift.starts_at).getTime()) / 3600000); return sum + Math.max(0, gross - Number(card.shift.break_minutes || 0) / 60); }, 0).toFixed(1)} Std.</small></em></header>';
if (source.includes(oldDayHeader)) {
  source = source.replace(oldDayHeader, newDayHeader);
  changed = true;
} else if (!source.includes('dayCards.reduce((sum, card)')) {
  throw new Error('Native schedule day header marker not found');
}

if (changed) fs.writeFileSync(schedulePath, source);
console.log(changed ? 'Applied native schedule stability patch.' : 'Native schedule stability patch already applied.');
