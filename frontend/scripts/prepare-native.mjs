import fs from 'node:fs';
import path from 'node:path';

const target = process.argv[2] || 'all';
const cwd = process.cwd();

function installAndroidLauncherArtwork(manifestPath) {
  const source = path.join(cwd, 'public', 'sicon.png');
  if (!fs.existsSync(source)) {
    throw new Error(`Official Android icon source not found: ${source}`);
  }

  // Native projects are recreated during Publisher/CI builds, so install the
  // exact public Play Store artwork after Capacitor generates Android. Point the
  // manifest directly at this drawable to prevent OEM launchers from falling
  // back to Capacitor's generated/default blue icon resources.
  const launcherDir = path.join(cwd, 'android', 'app', 'src', 'main', 'res', 'drawable-nodpi');
  const launcherPath = path.join(launcherDir, 'launcher_icon.png');
  fs.mkdirSync(launcherDir, { recursive: true });
  fs.copyFileSync(source, launcherPath);

  let xml = fs.readFileSync(manifestPath, 'utf8');
  if (!/<application\b/.test(xml)) {
    throw new Error('AndroidManifest.xml has no <application> element.');
  }

  if (/android:icon="[^"]+"/.test(xml)) {
    xml = xml.replace(/android:icon="[^"]+"/, 'android:icon="@drawable/launcher_icon"');
  } else {
    xml = xml.replace(/<application\b/, '<application android:icon="@drawable/launcher_icon"');
  }

  if (/android:roundIcon="[^"]+"/.test(xml)) {
    xml = xml.replace(/android:roundIcon="[^"]+"/, 'android:roundIcon="@drawable/launcher_icon"');
  } else {
    xml = xml.replace(/<application\b/, '<application android:roundIcon="@drawable/launcher_icon"');
  }

  if (!xml.includes('android:icon="@drawable/launcher_icon"')) {
    throw new Error('Failed to set android:icon to branded launcher artwork.');
  }
  if (!xml.includes('android:roundIcon="@drawable/launcher_icon"')) {
    throw new Error('Failed to set android:roundIcon to branded launcher artwork.');
  }

  fs.writeFileSync(manifestPath, xml);
  console.log('Installed exact A+ Solution Play Store artwork as Android launcher icon.');
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

  installAndroidLauncherArtwork(manifestPath);
  console.log('Prepared Android API 36, foreground-location permissions and branded launcher resources.');
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
