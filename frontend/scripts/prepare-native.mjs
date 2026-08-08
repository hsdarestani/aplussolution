import fs from 'node:fs';
import path from 'node:path';

const target = process.argv[2] || 'all';
const cwd = process.cwd();

function patchAndroid() {
  const manifestPath = path.join(cwd, 'android', 'app', 'src', 'main', 'AndroidManifest.xml');
  if (!fs.existsSync(manifestPath)) {
    if (target === 'android') throw new Error(`AndroidManifest.xml not found: ${manifestPath}`);
    return;
  }

  let xml = fs.readFileSync(manifestPath, 'utf8');
  const permissions = [
    'android.permission.ACCESS_COARSE_LOCATION',
    'android.permission.ACCESS_FINE_LOCATION',
  ];

  for (const permission of permissions) {
    if (!xml.includes(`android:name="${permission}"`)) {
      xml = xml.replace(
        /<application\b/,
        `    <uses-permission android:name="${permission}" />\n\n    <application`,
      );
    }
  }

  // The app deliberately does not request ACCESS_BACKGROUND_LOCATION.
  xml = xml.replace(/\s*<uses-permission android:name="android\.permission\.ACCESS_BACKGROUND_LOCATION"\s*\/>\s*/g, '\n');
  fs.writeFileSync(manifestPath, xml);

  // Public Google Play submissions must target Android 16 / API 36 from 31 Aug 2026.
  // Enforce it now so the first public build is already future-proof.
  const variablesPath = path.join(cwd, 'android', 'variables.gradle');
  if (!fs.existsSync(variablesPath)) {
    throw new Error(`variables.gradle not found: ${variablesPath}`);
  }
  let variables = fs.readFileSync(variablesPath, 'utf8');
  variables = variables
    .replace(/compileSdkVersion\s*=\s*\d+/, 'compileSdkVersion = 36')
    .replace(/targetSdkVersion\s*=\s*\d+/, 'targetSdkVersion = 36');
  if (!/compileSdkVersion\s*=\s*36/.test(variables) || !/targetSdkVersion\s*=\s*36/.test(variables)) {
    throw new Error('Could not enforce Android compileSdkVersion/targetSdkVersion 36.');
  }
  fs.writeFileSync(variablesPath, variables);

  console.log('Prepared Android API 36 and foreground-location permissions.');
}

function ensurePlistKey(plist, key, value) {
  if (plist.includes(`<key>${key}</key>`)) return plist;
  return plist.replace(
    /<\/dict>\s*<\/plist>/,
    `\t<key>${key}</key>\n\t<string>${value}</string>\n</dict>\n</plist>`,
  );
}

function patchIos() {
  const plistPath = path.join(cwd, 'ios', 'App', 'App', 'Info.plist');
  if (!fs.existsSync(plistPath)) {
    if (target === 'ios') throw new Error(`Info.plist not found: ${plistPath}`);
    return;
  }

  let plist = fs.readFileSync(plistPath, 'utf8');
  plist = ensurePlistKey(
    plist,
    'NSLocationWhenInUseUsageDescription',
    'Der Standort wird nur beim Ein- und Ausstempeln erfasst, um den vorgesehenen Einsatzort zu prüfen. Es findet keine Hintergrundortung statt.',
  );

  // No camera, photo-library, advertising tracking or background-location permission is added here.
  fs.writeFileSync(plistPath, plist);
  console.log('Prepared iOS foreground-location usage description.');
}

if (target === 'android' || target === 'all') patchAndroid();
if (target === 'ios' || target === 'all') patchIos();
