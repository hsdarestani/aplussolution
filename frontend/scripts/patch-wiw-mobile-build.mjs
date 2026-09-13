import { readFileSync, writeFileSync } from 'node:fs';

const path = new URL('../src/WiwScheduleMobile.tsx', import.meta.url);
const source = readFileSync(path, 'utf8');
let next = source;

// Worker eligibility must come from the employee's actual Zeitplan groups, not
// from a historic hard-coded name allow-list. Active/sync-invalid filtering is
// already applied when worker metadata is loaded in WiwScheduleMobile.
next = next.replace(/const WORKER_PICKER_NAMES = \[[\s\S]*?\];\n/, '');
next = next.replace(/const allowedWorkerNames = new Set\(WORKER_PICKER_NAMES\.map\(normalize\)\);\n/, '');

const legacyWorkerChoices = `  const workerChoices = useMemo<Choice[]>(() => workers
    .map((item: any) => ({ value: String(item.id), label: item.user_detail?.name || item.user_detail?.email || item.employee_number || 'Mitarbeiter' }))
    .filter((item: Choice) => allowedWorkerNames.has(normalize(item.label)))
    .sort((a: Choice, b: Choice) => a.label.localeCompare(b.label, 'de', { sensitivity: 'base' })), [workers]);`;

const oldZeitplanWorkerChoices = `  const workerChoices = useMemo<Choice[]>(() => {
    const selectedPosition = positions.find((item: any) => String(item.id) === form.position);
    const targetGroup = selectedPosition
      ? positionGroup(selectedPosition.name)
      : form.schedule_groups.length === 1
        ? form.schedule_groups[0]
        : '';

    return workers
      .filter((item: any) => {
        const label = item.user_detail?.name || item.user_detail?.email || item.employee_number || 'Mitarbeiter';
        if (!allowedWorkerNames.has(normalize(label))) return false;
        if (!targetGroup) return true;
        const groups = Array.isArray(item.schedule_groups) ? item.schedule_groups : [];
        return groups.includes(targetGroup);
      })
      .map((item: any) => ({ value: String(item.id), label: item.user_detail?.name || item.user_detail?.email || item.employee_number || 'Mitarbeiter' }))
      .sort((a: Choice, b: Choice) => a.label.localeCompare(b.label, 'de', { sensitivity: 'base' }));
  }, [workers, positions, form.position, form.schedule_groups]);`;

const scheduleAwareWorkerChoices = `  const workerChoices = useMemo<Choice[]>(() => {
    const selectedPosition = positions.find((item: any) => String(item.id) === form.position);
    const targetGroup = selectedPosition
      ? positionGroup(selectedPosition.name)
      : form.schedule_groups.length === 1
        ? form.schedule_groups[0]
        : '';

    return workers
      .filter((item: any) => {
        if (!targetGroup) return true;
        const groups = Array.isArray(item.schedule_groups) ? item.schedule_groups : [];
        return groups.includes(targetGroup);
      })
      .map((item: any) => ({ value: String(item.id), label: item.user_detail?.name || item.user_detail?.email || item.employee_number || 'Mitarbeiter' }))
      .sort((a: Choice, b: Choice) => a.label.localeCompare(b.label, 'de', { sensitivity: 'base' }));
  }, [workers, positions, form.position, form.schedule_groups]);`;

if (next.includes(legacyWorkerChoices)) {
  next = next.replace(legacyWorkerChoices, scheduleAwareWorkerChoices);
} else if (next.includes(oldZeitplanWorkerChoices)) {
  next = next.replace(oldZeitplanWorkerChoices, scheduleAwareWorkerChoices);
} else if (!next.includes(scheduleAwareWorkerChoices)) {
  throw new Error('Worker picker choices marker changed; update patch-wiw-mobile-build.mjs.');
}

// Single-person shifts should finish the worker selection immediately after the
// React state receives the new worker. Multi-person shifts deliberately remain
// open for further selections. Doing this in the component avoids the old
// synthetic DOM click race that could leave mobile sheets visually frozen.
const legacySingleChoice = "else if (limit === 1) onChange([choice.value]);";
const stableSingleChoice = "else if (limit === 1) { onChange([choice.value]); window.requestAnimationFrame(() => onClose()); }";
if (next.includes(legacySingleChoice)) {
  next = next.replace(legacySingleChoice, stableSingleChoice);
} else if (!next.includes(stableSingleChoice)) {
  throw new Error('Single-worker MultiChoiceSheet marker changed; update patch-wiw-mobile-build.mjs.');
}

if (next !== source) writeFileSync(path, next);
