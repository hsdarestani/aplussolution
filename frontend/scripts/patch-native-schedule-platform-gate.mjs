import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const schedulePath = path.resolve(here, '../src/WiwScheduleMobile.tsx');
const appPath = path.resolve(here, '../src/App.tsx');
let source = fs.readFileSync(schedulePath, 'utf8');
let appSource = fs.readFileSync(appPath, 'utf8');
let changed = false;
let appChanged = false;

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

// Expose the already-known authenticated role on the shell. This avoids a second
// auth/me request deciding whether the native admin calendar exists. On a slow or
// briefly-offline phone that extra request used to fail and the native layer would
// disappear, leaving the legacy web calendar inside the app.
const oldAppShell = '<IonApp className="mobile-first-app-shell-v1" data-view={mobileMenuOpen ? \'more\' : view}>';
const newAppShell = '<IonApp className="mobile-first-app-shell-v1" data-view={mobileMenuOpen ? \'more\' : view} data-role={user.role}>';
if (appSource.includes(oldAppShell)) {
  appSource = appSource.replace(oldAppShell, newAppShell);
  appChanged = true;
} else if (!appSource.includes('data-role={user.role}')) {
  throw new Error('App shell role marker not found');
}

const oldActiveSync = "    const root = document.getElementById('root');\n    const sync = () => setActive(Boolean(document.querySelector('.mobile-first-app-shell-v1[data-view=\"schedule\"]')));";
const newActiveSync = "    const root = document.getElementById('root');\n    const sync = () => {\n      const shell = document.querySelector<HTMLElement>('.mobile-first-app-shell-v1[data-view=\"schedule\"]');\n      setActive(Boolean(shell));\n      const role = shell?.dataset.role || '';\n      if (role) setManager(['admin', 'manager'].includes(role));\n    };";
if (source.includes(oldActiveSync)) {
  source = source.replace(oldActiveSync, newActiveSync);
  changed = true;
} else if (!source.includes("const role = shell?.dataset.role || '';")) {
  throw new Error('Native schedule shell observer marker not found');
}

// Keep auth/me only as a fallback for older shells. Once App has exposed a known
// admin/manager role, do not let a transient network call turn the native UI off.
const oldAuthGuard = '    if (!nativePlatform || !active || !mobile) return;';
const newAuthGuard = '    if (!nativePlatform || !active || !mobile || manager) return;';
if (source.includes(oldAuthGuard)) {
  source = source.replace(oldAuthGuard, newAuthGuard);
  changed = true;
}

if (!source.includes('if (!nativePlatform || !active || !mobile || !manager) return null;')) {
  throw new Error('Native schedule platform gate was not applied to render guard');
}
if (!appSource.includes('data-role={user.role}')) {
  throw new Error('Authenticated role is not exposed on app shell');
}

if (changed) fs.writeFileSync(schedulePath, source);
if (appChanged) fs.writeFileSync(appPath, appSource);
console.log(changed || appChanged ? 'Applied native-only schedule platform gate and resilient role activation.' : 'Native schedule platform gate already applied.');
