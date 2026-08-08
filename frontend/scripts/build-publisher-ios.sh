#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FRONTEND="$ROOT/frontend"
cd "$FRONTEND"

: "${IOS_TEAM_ID:?Publisher must provide IOS_TEAM_ID}"
: "${IOS_BUNDLE_ID:?Publisher must provide IOS_BUNDLE_ID}"
: "${APP_VERSION_NAME:?Publisher must provide APP_VERSION_NAME}"
: "${APP_BUILD_NUMBER:?Publisher must provide APP_BUILD_NUMBER}"
: "${IOS_CODE_SIGN_IDENTITY:?Publisher must provide IOS_CODE_SIGN_IDENTITY}"
: "${IOS_PROVISIONING_PROFILE_SPECIFIER:?Publisher must provide IOS_PROVISIONING_PROFILE_SPECIFIER}"
: "${IOS_SIGNING_KEYCHAIN:?Publisher must provide IOS_SIGNING_KEYCHAIN}"

npm install --no-audit --no-fund
npm run build
rm -rf ios
npx cap add ios
npx cap sync ios
node scripts/prepare-native.mjs ios

# Always regenerate the native iOS AppIcon from the user-approved source icon.
# The iOS project is recreated on every Publisher build, so changing only a web
# icon under public/ would otherwise be lost and App Store Connect would keep
# showing Capacitor's/default native icon.
ICON_SOURCE="$FRONTEND/public/sicon.png"
ICON_ASSET_DIR="$FRONTEND/resources"
test -f "$ICON_SOURCE"
rm -rf "$ICON_ASSET_DIR"
mkdir -p "$ICON_ASSET_DIR"
cp "$ICON_SOURCE" "$ICON_ASSET_DIR/icon.png"

# Use the official Capacitor asset generator to crop/resize the source and write
# the real Xcode AppIcon.appiconset. Pin the version so future builds are stable.
npx --yes @capacitor/assets@3.0.5 generate \
  --ios \
  --assetPath "$ICON_ASSET_DIR" \
  --iconBackgroundColor '#00142f' \
  --iconBackgroundColorDark '#00142f'

APP_ICON_SET="$FRONTEND/ios/App/App/Assets.xcassets/AppIcon.appiconset"
test -d "$APP_ICON_SET"
test -f "$APP_ICON_SET/Contents.json"
echo "Generated native iOS AppIcon from public/sicon.png."

# Configure signing only on the generated App target. Passing the provisioning
# profile as an xcodebuild command-line build setting makes it inherit into all
# CocoaPods targets, which do not support provisioning profiles and causes
# ARCHIVE FAILED / exit code 65.
python3 scripts/patch-ios-project-signing.py

ARCHIVE_PATH="$FRONTEND/ios/build/APlusWorkforce.xcarchive"
EXPORT_PATH="$FRONTEND/ios/build/export"
EXPORT_OPTIONS="$FRONTEND/ios/ExportOptions.plist"
mkdir -p "$EXPORT_PATH"

# The App target now contains the Publisher's manual App Store signing settings.
# Do not repeat app-only signing values on the xcodebuild command line because
# command-line settings propagate to Pods.xcodeproj as well.
xcodebuild \
  -workspace ios/App/App.xcworkspace \
  -scheme App \
  -configuration Release \
  -destination 'generic/platform=iOS' \
  -archivePath "$ARCHIVE_PATH" \
  archive

cat > "$EXPORT_OPTIONS" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>method</key><string>app-store-connect</string>
  <key>signingStyle</key><string>manual</string>
  <key>teamID</key><string>${IOS_TEAM_ID}</string>
  <key>signingCertificate</key><string>${IOS_CODE_SIGN_IDENTITY}</string>
  <key>provisioningProfiles</key>
  <dict>
    <key>${IOS_BUNDLE_ID}</key><string>${IOS_PROVISIONING_PROFILE_SPECIFIER}</string>
  </dict>
  <key>destination</key><string>export</string>
  <key>manageAppVersionAndBuildNumber</key><false/>
  <key>stripSwiftSymbols</key><true/>
  <key>uploadSymbols</key><true/>
</dict>
</plist>
PLIST

xcodebuild \
  -exportArchive \
  -archivePath "$ARCHIVE_PATH" \
  -exportPath "$EXPORT_PATH" \
  -exportOptionsPlist "$EXPORT_OPTIONS"

test -n "$(find "$EXPORT_PATH" -maxdepth 1 -name '*.ipa' -print -quit)"
echo "Publisher iOS IPA created successfully."
