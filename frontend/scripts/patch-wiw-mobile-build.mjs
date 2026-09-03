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
