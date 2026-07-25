import { readFileSync, writeFileSync } from 'node:fs';

const path = new URL('../src/App.tsx', import.meta.url);
const source = readFileSync(path, 'utf8');
const original = `          type="color"
          label="Farbe"`;
const compatible = `          {...({ type: 'color' } as any)}
          label="Farbe"`;

if (source.includes(original)) {
  writeFileSync(path, source.replace(original, compatible));
}
