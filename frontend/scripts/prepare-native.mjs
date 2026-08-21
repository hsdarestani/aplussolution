import fs from 'node:fs';
import path from 'node:path';

const target = process.argv[2] || 'all';
const cwd = process.cwd();
const requirePush = ['1', 'true', 'yes'].includes(String(process.env.REQUIRE_NATIVE_PUSH || '').toLowerCase());

function installAndroidLauncherArtwork(manifestPath) {
  const source = path.join(cwd, 'public', 'sicon.png');
  if (!fs.existsSync(source)) throw new Error(`Official Android icon source not found: ${source}`);
  const launcherDir = path.join(cwd, 'android', 'app', 'src', 'main', 'res', 'drawable-nodpi');
  const launcherPath = path.join(launcherDir, 'launcher_icon.png');
  fs.mkdirSync(launcherDir, { recursive: true });
  fs.copyFileSync(source, launcherPath);

  let xml = fs.readFileSync(manifestPath, 'utf8');
  if (!/<application\b/.test(xml)) throw new Error('AndroidManifest.xml has no <application> element.');
  xml = /android:icon="[^"]+"/.test(xml)
    ? xml.replace(/android:icon="[^"]+"/, 'android:icon="@drawable/launcher_icon"')
    : xml.replace(/<application\b/, '<application android:icon="@drawable/launcher_icon"');
  xml = /android:roundIcon="[^"]+"/.test(xml)
    ? xml.replace(/android:roundIcon="[^"]+"/, 'android:roundIcon="@drawable/launcher_icon"')
    : xml.replace(/<application\b/, '<application android:roundIcon="@drawable/launcher_icon"');
  fs.writeFileSync(manifestPath, xml);
}

function installGoogleServices() {
  const targetPath = path.join(cwd, 'android', 'app', 'google-services.json');
  const encoded = String(process.env.GOOGLE_SERVICES_JSON_BASE64 || '').trim();
  const raw = String(process.env.GOOGLE_SERVICES_JSON || '').trim();
  const checkedIn = path.join(cwd, 'firebase', 'google-services.json');
  if (encoded) {
    fs.writeFileSync(targetPath, Buffer.from(encoded, 'base64'));
  } else if (raw) {
    fs.writeFileSync(targetPath, raw);
  } else if (fs.existsSync(checkedIn)) {
    fs.copyFileSync(checkedIn, targetPath);
  }
  if (requirePush && !fs.existsSync(targetPath)) {
    throw new Error('Native Android push requires GOOGLE_SERVICES_JSON_BASE64, GOOGLE_SERVICES_JSON, or firebase/google-services.json.');
  }
  if (fs.existsSync(targetPath)) console.log('Firebase google-services.json installed for Android push.');
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
    'android.permission.POST_NOTIFICATIONS',
  ];
  for (const permission of permissions) {
    if (!xml.includes(`android:name="${permission}"`)) {
      xml = xml.replace(/<application\b/, `    <uses-permission android:name="${permission}" />\n\n    <application`);
    }
  }
  xml = xml.replace(/\s*<uses-permission android:name="android\.permission\.ACCESS_BACKGROUND_LOCATION"\s*\/>\s*/g, '\n');
  fs.writeFileSync(manifestPath, xml);

  const variablesPath = path.join(cwd, 'android', 'variables.gradle');
  if (!fs.existsSync(variablesPath)) throw new Error(`variables.gradle not found: ${variablesPath}`);
  let variables = fs.readFileSync(variablesPath, 'utf8');
  variables = variables
    .replace(/compileSdkVersion\s*=\s*\d+/, 'compileSdkVersion = 36')
    .replace(/targetSdkVersion\s*=\s*\d+/, 'targetSdkVersion = 36');
  if (!/compileSdkVersion\s*=\s*36/.test(variables) || !/targetSdkVersion\s*=\s*36/.test(variables)) {
    throw new Error('Could not enforce Android compileSdkVersion/targetSdkVersion 36.');
  }
  fs.writeFileSync(variablesPath, variables);
  installGoogleServices();
  installAndroidLauncherArtwork(manifestPath);
  console.log('Prepared Android API 36, foreground location and native push permissions.');
}

function ensurePlistKey(plist, key, value) {
  if (plist.includes(`<key>${key}</key>`)) return plist;
  return plist.replace(/<\/dict>\s*<\/plist>/, `\t<key>${key}</key>\n\t<string>${value}</string>\n</dict>\n</plist>`);
}

function ensurePlistBooleanKey(plist, key, value) {
  if (plist.includes(`<key>${key}</key>`)) return plist;
  return plist.replace(/<\/dict>\s*<\/plist>/, `\t<key>${key}</key>\n\t<${value ? 'true' : 'false'}/>\n</dict>\n</plist>`);
}

function patchIosPush() {
  const appDir = path.join(cwd, 'ios', 'App', 'App');
  const entitlementsPath = path.join(appDir, 'App.entitlements');
  fs.writeFileSync(entitlementsPath, `<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0">\n<dict>\n\t<key>aps-environment</key>\n\t<string>production</string>\n</dict>\n</plist>\n`);

  const pbxPath = path.join(cwd, 'ios', 'App', 'App.xcodeproj', 'project.pbxproj');
  if (!fs.existsSync(pbxPath)) throw new Error(`Xcode project not found: ${pbxPath}`);
  let pbx = fs.readFileSync(pbxPath, 'utf8');
  if (!pbx.includes('CODE_SIGN_ENTITLEMENTS = App/App.entitlements;')) {
    pbx = pbx.replace(/(PRODUCT_BUNDLE_IDENTIFIER = de\.aplussolution\.workforce;)/g, 'CODE_SIGN_ENTITLEMENTS = App/App.entitlements;\n\t\t\t\t$1');
  }
  if (!pbx.includes('CODE_SIGN_ENTITLEMENTS = App/App.entitlements;')) {
    throw new Error('Could not attach App.entitlements to the Xcode target.');
  }
  fs.writeFileSync(pbxPath, pbx);

  const delegatePath = path.join(appDir, 'AppDelegate.swift');
  if (!fs.existsSync(delegatePath)) throw new Error(`AppDelegate.swift not found: ${delegatePath}`);
  let delegate = fs.readFileSync(delegatePath, 'utf8');
  if (!delegate.includes('capacitorDidRegisterForRemoteNotifications')) {
    const insertion = `\n    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {\n        NotificationCenter.default.post(name: .capacitorDidRegisterForRemoteNotifications, object: deviceToken)\n    }\n\n    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {\n        NotificationCenter.default.post(name: .capacitorDidFailToRegisterForRemoteNotifications, object: error)\n    }\n`;
    const marker = delegate.lastIndexOf('\n}');
    if (marker < 0) throw new Error('Could not patch AppDelegate for APNs callbacks.');
    delegate = `${delegate.slice(0, marker)}${insertion}${delegate.slice(marker)}`;
  }
  fs.writeFileSync(delegatePath, delegate);
  console.log('Prepared iOS Push Notifications entitlement and APNs callbacks.');
}

function patchIos() {
  const plistPath = path.join(cwd, 'ios', 'App', 'App', 'Info.plist');
  if (!fs.existsSync(plistPath)) {
    if (target === 'ios') throw new Error(`Info.plist not found: ${plistPath}`);
    return;
  }
  let plist = fs.readFileSync(plistPath, 'utf8');
  plist = ensurePlistKey(plist, 'NSLocationWhenInUseUsageDescription', 'Der Standort wird nur beim Ein- und Ausstempeln erfasst, um den vorgesehenen Einsatzort zu prüfen. Es findet keine Hintergrundortung statt.');
  plist = ensurePlistBooleanKey(plist, 'ITSAppUsesNonExemptEncryption', false);
  fs.writeFileSync(plistPath, plist);
  patchIosPush();
  console.log('Prepared iOS foreground-location, export compliance and native push.');
}

if (target === 'android' || target === 'all') patchAndroid();
if (target === 'ios' || target === 'all') patchIos();
