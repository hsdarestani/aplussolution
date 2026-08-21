import { readFileSync, writeFileSync } from 'node:fs';

const path = new URL('../src/App.tsx', import.meta.url);
const source = readFileSync(path, 'utf8');
let next = source;

const originalColor = `          type="color"
          label="Farbe"`;
const compatibleColor = `          {...({ type: 'color' } as any)}
          label="Farbe"`;

if (next.includes(originalColor)) {
  next = next.replace(originalColor, compatibleColor);
}

const localDateHelpers = `const dateTime = (input?: string) => (input ? new Date(input).toLocaleString('de-DE') : '–');
const dateOnly = (input?: string) => (input ? new Date(input).toLocaleDateString('de-DE') : '–');`;
const berlinDateHelpers = `const BUSINESS_TIME_ZONE = 'Europe/Berlin';
const dateTime = (input?: string) =>
  input ? new Date(input).toLocaleString('de-DE', { timeZone: BUSINESS_TIME_ZONE }) : '–';
const dateOnly = (input?: string) =>
  input ? new Date(input).toLocaleDateString('de-DE', { timeZone: BUSINESS_TIME_ZONE }) : '–';`;

if (next.includes(localDateHelpers)) {
  next = next.replace(localDateHelpers, berlinDateHelpers);
} else if (!next.includes("const BUSINESS_TIME_ZONE = 'Europe/Berlin';")) {
  throw new Error('Legacy App.tsx date helper marker changed; update prepare-build.mjs.');
}

if (next !== source) {
  writeFileSync(path, next);
}
