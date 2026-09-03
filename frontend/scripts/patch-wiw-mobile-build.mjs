import { readFileSync, writeFileSync } from 'node:fs';

const path = new URL('../src/WiwScheduleMobile.tsx', import.meta.url);
const source = readFileSync(path, 'utf8');
let next = source;

// The employee account uses the spelling Somodi. Keep the historic Somodo
// spelling in the allow-list as an alias so existing cached/imported data remains
// compatible while the actual employee is no longer filtered out of the picker.
const legacyIzabella = "  'Izabella Somodo',";
const izabellaAliases = "  'Izabella Somodo',\n  'Izabella Somodi',";
if (!next.includes("  'Izabella Somodi',")) {
  if (!next.includes(legacyIzabella)) {
    throw new Error('Izabella worker allow-list marker changed; update patch-wiw-mobile-build.mjs.');
  }
  next = next.replace(legacyIzabella, izabellaAliases);
}

// Filter candidates inside React from the actual shift position / Zeitplan.
// This is intentionally not a DOM-hiding enhancer: when editing Housekeeping,
// Service candidates must never be mounted in the selection sheet at all.
const legacyWorkerChoices = `  const workerChoices = useMemo<Choice[]>(() => workers
    .map((item: any) => ({ value: String(item.id), label: item.user_detail?.name || item.user_detail?.email || item.employee_number || 'Mitarbeiter' }))
    .filter((item: Choice) => allowedWorkerNames.has(normalize(item.label)))
    .sort((a: Choice, b: Choice) => a.label.localeCompare(b.label, 'de', { sensitivity: 'base' })), [workers]);`;
const zeitplanWorkerChoices = `  const workerChoices = useMemo<Choice[]>(() => {
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
if (next.includes(legacyWorkerChoices)) {
  next = next.replace(legacyWorkerChoices, zeitplanWorkerChoices);
} else if (!next.includes('const targetGroup = selectedPosition')) {
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
