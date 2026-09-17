import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const schedulePath = path.resolve(here, '../src/WiwScheduleMobile.tsx');
let source = fs.readFileSync(schedulePath, 'utf8');
let changed = false;

// The compact Dienstplan is the native Capacitor UI. Rendering it in a normal
// browser purely because the viewport is <= 900px caused the legacy web calendar
// and native portal to fight for the same .app-main tree. That could hide the web
// "+" action, duplicate layers and leave touch/scroll handlers in a frozen state.
// Keep the two products explicit: browser => web calendar, Capacitor => native UI.
const functionMarker = 'export default function WiwScheduleMobile() {\n';
const nativeMarker = '  const nativePlatform = Capacitor.isNativePlatform();\n';
if (!source.includes(nativeMarker)) {
  if (!source.includes(functionMarker)) throw new Error('WiwScheduleMobile function marker not found');
  source = source.replace(functionMarker, `${functionMarker}${nativeMarker}`);
  changed = true;
}

const replacements = [
  ['    if (!active || !mobile) return;', '    if (!nativePlatform || !active || !mobile) return;'],
  ['    if (!active || !mobile || !manager) return;', '    if (!nativePlatform || !active || !mobile || !manager) return;'],
  ['  if (!active || !mobile || !manager) return null;', '  if (!nativePlatform || !active || !mobile || !manager) return null;'],
];

for (const [before, after] of replacements) {
  if (source.includes(before)) {
    source = source.split(before).join(after);
    changed = true;
  }
}

if (!source.includes('if (!nativePlatform || !active || !mobile || !manager) return null;')) {
  throw new Error('Native schedule platform gate was not applied to render guard');
}

if (changed) fs.writeFileSync(schedulePath, source);
console.log(changed ? 'Applied native-only schedule platform gate.' : 'Native schedule platform gate already applied.');
