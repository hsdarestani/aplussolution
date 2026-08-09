import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const target = process.argv[2] || 'all';
const cwd = process.cwd();

function generateAndroidLauncherAssets() {
  const source = path.join(cwd, 'public', 'sicon.png');
  if (!fs.existsSync(source)) {
    throw new Error(`Official Android icon source not found: ${source}`);
  }

  // Keep the source of truth in public/sicon.png (the same finished artwork used
  // for the store) and materialize a clean Capacitor asset set only for the build.
  // Using icon-only.png makes @capacitor/assets create legacy + adaptive launcher
  // resources with a safe zone instead of shipping Capacitor's default icon.
  const assetDir = path.join(cwd, '.native-assets-android');
  fs.rmSync(assetDir, { recursive: true, force: true });
  fs.mkdirSync(assetDir, { recursive: true });
  fs.copyFileSync(source, path.join(assetDir, 'icon-only.png'));

  const npx = process.platform === 'win32' ? 'npx.cmd' : 'npx';
  try {
    execFileSync(
      npx,
      [
        '@capacitor/assets',
        'generate',
        '--android',
        '--asset-path',
        assetDir,
        '--iconBackgroundColor',
        '#07172F',
        '--iconBackgroundColorDark',
        '#07172F',
        '--splashBackgroundColor',
        '#07172F',
        '--splashBackgroundColorDark',
        '#07172F',
        '--logoSplashScale',
        '0.34',
      ],
      { cwd, stdio: 'inherit' },
    );
  } finally {
    fs.rmSync(assetDir, { recursive: true, force: true });
  }

  console.log('Generated A+ Solution Android legacy/adaptive launcher icons from public/sicon.png.');
}

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

  generateAndroidLauncherAssets();
  console.log('Prepared Android API 36, foreground-location permissions and official launcher assets.');
}

function ensurePlistKey(plist, key, value) {
  if (plist.includes(`<key>${key}</key>`)) return plist;
  return plist.replace(
    /<\/dict>\s*<\/plist>/,
    `\t<key>${key}</key>\n\t<string>${value}</string>\n</dict>\n</plist>`,
  );
}

function ensurePlistBooleanKey(plist, key, value) {
  if (plist.includes(`<key>${key}</key>`)) return plist;
  return plist.replace(
    /<\/dict>\s*<\/plist>/,
    `\t<key>${key}</key>\n\t<${value ? 'true' : 'false'}/>\n</dict>\n</plist>`,
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
  // The app relies on standard encryption provided by Apple OS networking APIs and
  // does not ship proprietary/non-exempt cryptography.
  plist = ensurePlistBooleanKey(plist, 'ITSAppUsesNonExemptEncryption', false);

  // No camera, photo-library, advertising tracking or background-location permission is added here.
  fs.writeFileSync(plistPath, plist);
  console.log('Prepared iOS foreground-location and export-compliance declarations.');
}

if (target === 'android' || target === 'all') patchAndroid();
if (target === 'ios' || target === 'all') patchIos();
