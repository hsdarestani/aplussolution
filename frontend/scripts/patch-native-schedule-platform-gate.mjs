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

// The compact Dienstplan is intentionally shared by mobile web and Capacitor.
// The old native-only gate accidentally sent mobile browsers back to ScheduleV2.
// Keep the <=900px compact view on both platforms; isolation from the legacy
// schedule is handled in CSS so only one schedule layer can paint or receive input.
const nativeMarker = '  const nativePlatform = Capacitor.isNativePlatform();\n';
if (source.includes(nativeMarker)) {
  source = source.replace(nativeMarker, '');
  changed = true;
}

const guardReplacements = [
  ['if (!nativePlatform || !active || !mobile || manager) return;', 'if (!active || !mobile || manager) return;'],
  ['if (!nativePlatform || !active || !mobile) return;', 'if (!active || !mobile) return;'],
  ['if (!nativePlatform || !active || !mobile || !manager) return;', 'if (!active || !mobile || !manager) return;'],
  ['if (!nativePlatform || !active || !mobile || !manager) return null;', 'if (!active || !mobile || !manager) return null;'],
];
for (const [before, after] of guardReplacements) {
  if (source.includes(before)) {
    source = source.split(before).join(after);
    changed = true;
  }
}

// Expose the already authenticated role on the shell. This avoids an extra
// auth/me request deciding whether the compact admin calendar is allowed to mount.
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
  throw new Error('Compact schedule shell observer marker not found');
}

// auth/me is only a fallback for older shells that do not expose a role yet.
const authGuard = '    if (!active || !mobile) return;';
const resilientAuthGuard = '    if (!active || !mobile || manager) return;';
if (source.includes(authGuard)) {
  source = source.replace(authGuard, resilientAuthGuard);
  changed = true;
}

if (source.includes('nativePlatform ||')) {
  throw new Error('Native-only schedule guard is still present');
}
if (!source.includes('if (!active || !mobile || !manager) return null;')) {
  throw new Error('Shared mobile schedule render guard is missing');
}
if (!appSource.includes('data-role={user.role}')) {
  throw new Error('Authenticated role is not exposed on app shell');
}

if (changed) fs.writeFileSync(schedulePath, source);
if (appChanged) fs.writeFileSync(appPath, appSource);
console.log(changed || appChanged ? 'Applied shared mobile schedule activation with resilient role detection.' : 'Shared mobile schedule activation already applied.');
