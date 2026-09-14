import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const target = process.argv[2] || 'all';
const cwd = process.cwd();
const isStaging = String(process.env.APP_ENV || '').toLowerCase() === 'staging';
const nativeAppId = String(
  process.env.CAPACITOR_APP_ID ||
    process.env.IOS_BUNDLE_ID ||
    (isStaging ? 'de.aplussolution.staging' : 'de.aplussolution.workforce'),
).trim();
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

function validateGoogleServices(targetPath) {
  if (!fs.existsSync(targetPath)) return;
  let parsed;
  try {
    parsed = JSON.parse(fs.readFileSync(targetPath, 'utf8'));
  } catch (error) {
    throw new Error(`Invalid Firebase google-services.json: ${error instanceof Error ? error.message : String(error)}`);
  }
  const packageNames = (parsed.client || [])
    .map((client) => client?.client_info?.android_client_info?.package_name)
    .filter(Boolean);
  if (!packageNames.includes(nativeAppId)) {
    throw new Error(
      `Firebase google-services.json does not contain Android package ${nativeAppId}. Found: ${packageNames.join(', ') || 'none'}`,
    );
  }
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
  } else if (!isStaging && fs.existsSync(checkedIn)) {
    fs.copyFileSync(checkedIn, targetPath);
  }
  if (requirePush && !fs.existsSync(targetPath)) {
    throw new Error(
      isStaging
        ? 'Native Android staging push requires a staging GOOGLE_SERVICES_JSON_BASE64 or GOOGLE_SERVICES_JSON.'
        : 'Native Android push requires GOOGLE_SERVICES_JSON_BASE64, GOOGLE_SERVICES_JSON, or firebase/google-services.json.',
    );
  }
  if (fs.existsSync(targetPath)) {
    validateGoogleServices(targetPath);
    console.log(`Firebase google-services.json installed for Android package ${nativeAppId}.`);
  } else if (isStaging) {
    console.log('Staging Android build has no Firebase config; native push is disabled until staging Firebase credentials are supplied.');
  }
}

function installAndroidNotificationBranding(manifestPath) {
  const assetsDir = path.join(cwd, 'native-assets', 'android');
  const soundSource = path.join(assetsDir, 'solution_signature.wav');
  const iconSource = path.join(assetsDir, 'ic_stat_aplus.xml');
  if (!fs.existsSync(soundSource)) throw new Error(`Android notification sound source not found: ${soundSource}`);
  if (!fs.existsSync(iconSource)) throw new Error(`Android notification icon source not found: ${iconSource}`);

  const resDir = path.join(cwd, 'android', 'app', 'src', 'main', 'res');
  const rawDir = path.join(resDir, 'raw');
  const drawableDir = path.join(resDir, 'drawable');
  fs.mkdirSync(rawDir, { recursive: true });
  fs.mkdirSync(drawableDir, { recursive: true });
  fs.copyFileSync(soundSource, path.join(rawDir, 'solution_signature.wav'));
  fs.copyFileSync(iconSource, path.join(drawableDir, 'ic_stat_aplus.xml'));

  let xml = fs.readFileSync(manifestPath, 'utf8');
  const iconMeta = '        <meta-data android:name="com.google.firebase.messaging.default_notification_icon" android:resource="@drawable/ic_stat_aplus" />';
  const channelMeta = '        <meta-data android:name="com.google.firebase.messaging.default_notification_channel_id" android:value="aplus_updates_signature_v1" />';
  if (!xml.includes('com.google.firebase.messaging.default_notification_icon')) {
    xml = xml.replace(/<application\b[^>]*>/, (match) => `${match}\n${iconMeta}`);
  }
  if (!xml.includes('com.google.firebase.messaging.default_notification_channel_id')) {
    xml = xml.replace(/<application\b[^>]*>/, (match) => `${match}\n${channelMeta}`);
  }
  fs.writeFileSync(manifestPath, xml);
  console.log('Installed Android A+ notification icon and Signature Motif sound.');
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
  installAndroidNotificationBranding(manifestPath);
  console.log(`Prepared Android ${nativeAppId}, API 36, foreground location, native push permissions and notification branding.`);
}

function ensurePlistKey(plist, key, value) {
  if (plist.includes(`<key>${key}</key>`)) return plist;
  return plist.replace(/<\/dict>\s*<\/plist>/, `\t<key>${key}</key>\n\t<string>${value}</string>\n</dict>\n</plist>`);
}

function ensurePlistBooleanKey(plist, key, value) {
  if (plist.includes(`<key>${key}</key>`)) return plist;
  return plist.replace(/<\/dict>\s*<\/plist>/, `\t<key>${key}</key>\n\t<${value ? 'true' : 'false'}/>\n</dict>\n</plist>`);
}

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function patchIosPush() {
  const appDir = path.join(cwd, 'ios', 'App', 'App');
  const entitlementsPath = path.join(appDir, 'App.entitlements');
  fs.writeFileSync(entitlementsPath, `<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0">\n<dict>\n\t<key>aps-environment</key>\n\t<string>production</string>\n</dict>\n</plist>\n`);

  const pbxPath = path.join(cwd, 'ios', 'App', 'App.xcodeproj', 'project.pbxproj');
  if (!fs.existsSync(pbxPath)) throw new Error(`Xcode project not found: ${pbxPath}`);
  let pbx = fs.readFileSync(pbxPath, 'utf8');
  if (!pbx.includes('CODE_SIGN_ENTITLEMENTS = App/App.entitlements;')) {
    const bundlePattern = new RegExp(`(PRODUCT_BUNDLE_IDENTIFIER = ${escapeRegex(nativeAppId)};)`, 'g');
    pbx = pbx.replace(bundlePattern, 'CODE_SIGN_ENTITLEMENTS = App/App.entitlements;\n\t\t\t\t$1');
  }
  if (!pbx.includes('CODE_SIGN_ENTITLEMENTS = App/App.entitlements;')) {
    throw new Error(`Could not attach App.entitlements to the Xcode target for ${nativeAppId}.`);
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
  console.log(`Prepared iOS Push Notifications entitlement and APNs callbacks for ${nativeAppId}.`);
}

function patchIosFilePrivacy() {
  const appDir = path.join(cwd, 'ios', 'App', 'App');
  const privacyPath = path.join(appDir, 'PrivacyInfo.xcprivacy');
  execFileSync('python3', ['-c', `
import os, plistlib, sys
p = sys.argv[1]
data = plistlib.load(open(p, 'rb')) if os.path.exists(p) else {}
entries = data.setdefault('NSPrivacyAccessedAPITypes', [])
category = 'NSPrivacyAccessedAPICategoryFileTimestamp'
entry = next((item for item in entries if item.get('NSPrivacyAccessedAPIType') == category), None)
if entry is None:
    entry = {'NSPrivacyAccessedAPIType': category, 'NSPrivacyAccessedAPITypeReasons': []}
    entries.append(entry)
reasons = entry.setdefault('NSPrivacyAccessedAPITypeReasons', [])
if 'C617.1' not in reasons:
    reasons.append('C617.1')
with open(p, 'wb') as output:
    plistlib.dump(data, output)
`, privacyPath]);
  const pbxPath = path.join(cwd, 'ios', 'App', 'App.xcodeproj', 'project.pbxproj');
  let pbx = fs.readFileSync(pbxPath, 'utf8');
  if (!pbx.includes('PrivacyInfo.xcprivacy in Resources')) {
    pbx = pbx.replace('/* Begin PBXBuildFile section */', '/* Begin PBXBuildFile section */\n\t\tA90100000000000000000001 /* PrivacyInfo.xcprivacy in Resources */ = {isa = PBXBuildFile; fileRef = A90100000000000000000002; };');
    pbx = pbx.replace('/* Begin PBXFileReference section */', '/* Begin PBXFileReference section */\n\t\tA90100000000000000000002 /* PrivacyInfo.xcprivacy */ = {isa = PBXFileReference; lastKnownFileType = text.xml; path = App/PrivacyInfo.xcprivacy; sourceTree = SOURCE_ROOT; };');
    pbx = pbx.replace(/(isa = PBXResourcesBuildPhase;[\s\S]*?files = \()/, '$1\n\t\t\t\tA90100000000000000000001 /* PrivacyInfo.xcprivacy in Resources */,');
    if ((pbx.match(/A90100000000000000000001/g) || []).length !== 2) throw new Error('Could not attach PDF filesystem privacy manifest.');
    fs.writeFileSync(pbxPath, pbx);
  }
}

function patchIos() {
  const plistPath = path.join(cwd, 'ios', 'App', 'App', 'Info.plist');
  if (!fs.existsSync(plistPath)) {
    if (target === 'ios') throw new Error(`Info.plist not found: ${plistPath}`);
    return;
  }
  let plist = fs.readFileSync(plistPath, 'utf8');
  plist = ensurePlistKey(plist, 'NSLocationWhenInUseUsageDescription', 'Der Standort wird nur beim Ein- und Ausstempeln erfasst, um den vorgesehenen Einsatzort zu prüfen. Es findet keine Hintergrundortung statt.');
  // Apple validates binaries against sensitive APIs referenced by bundled SDKs as
  // well as APIs called directly by the app. Capacitor's location stack can make
  // the Always/When-In-Use purpose key mandatory even though A+ Solution only
  // requests foreground location. Keep the text explicit so App Review and users
  // understand that no background tracking is performed.
  plist = ensurePlistKey(plist, 'NSLocationAlwaysAndWhenInUseUsageDescription', 'Diese Standortberechtigung wird technisch für die Standortfunktion benötigt. A+ Solution verwendet den Standort ausschließlich beim Ein- und Ausstempeln im Vordergrund, um den vorgesehenen Einsatzort zu prüfen. Eine Hintergrundortung findet nicht statt.');
  plist = ensurePlistBooleanKey(plist, 'ITSAppUsesNonExemptEncryption', false);
  fs.writeFileSync(plistPath, plist);

  // Production requires native push and keeps the APNs entitlement. Staging has
  // no separate APNs/Firebase credentials yet, so do not demand an Apple profile
  // with Push Notifications until REQUIRE_NATIVE_PUSH=1 is explicitly enabled.
  if (!isStaging || requirePush) {
    patchIosPush();
  } else {
    console.log('Staging iOS build has no native push requirement; APNs entitlement is disabled until staging push credentials are supplied.');
  }

  patchIosFilePrivacy();
  console.log(
    `Prepared iOS ${nativeAppId}, foreground-location purpose strings, export compliance${!isStaging || requirePush ? ' and native push' : ''}.`,
  );
}

if (target === 'android' || target === 'all') patchAndroid();
if (target === 'ios' || target === 'all') patchIos();
