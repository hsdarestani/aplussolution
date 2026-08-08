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
  console.log('Prepared Android foreground-location permissions.');
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
