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

# Force the exact user-approved icon into the native Xcode AppIcon set.
# Do this directly instead of relying on a generator, because the iOS project is
# recreated by Capacitor on every Publisher build.
ICON_SOURCE="$FRONTEND/public/sicon.png"
APP_ICON_SET="$FRONTEND/ios/App/App/Assets.xcassets/AppIcon.appiconset"
test -f "$ICON_SOURCE"
test -d "$APP_ICON_SET"
test -f "$APP_ICON_SET/Contents.json"

ICON_COUNT=0
while IFS= read -r -d '' ICON_FILE; do
  WIDTH="$(sips -g pixelWidth "$ICON_FILE" | awk '/pixelWidth:/ {print $2}')"
  HEIGHT="$(sips -g pixelHeight "$ICON_FILE" | awk '/pixelHeight:/ {print $2}')"
  test -n "$WIDTH"
  test -n "$HEIGHT"
  sips -z "$HEIGHT" "$WIDTH" "$ICON_SOURCE" --out "$ICON_FILE" >/dev/null
  ICON_COUNT=$((ICON_COUNT + 1))
done < <(find "$APP_ICON_SET" -type f -name '*.png' -print0)

if [ "$ICON_COUNT" -lt 1 ]; then
  echo "No native AppIcon PNG files were found to replace." >&2
  exit 1
fi

echo "Replaced $ICON_COUNT native AppIcon PNG file(s) from public/sicon.png."
echo "Source icon SHA256: $(shasum -a 256 "$ICON_SOURCE" | awk '{print $1}')"
find "$APP_ICON_SET" -type f -name '*.png' -maxdepth 1 -print -exec shasum -a 256 {} \;

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

# Verify that the archived app actually contains an app icon before export.
ARCHIVED_APP="$ARCHIVE_PATH/Products/Applications/App.app"
test -d "$ARCHIVED_APP"
ARCHIVED_ICON_COUNT="$(find "$ARCHIVED_APP" -maxdepth 1 -type f \( -name 'AppIcon*.png' -o -name 'Icon*.png' \) | wc -l | tr -d ' ')"
echo "Archived app icon file count: $ARCHIVED_ICON_COUNT"
find "$ARCHIVED_APP" -maxdepth 1 -type f \( -name 'AppIcon*.png' -o -name 'Icon*.png' \) -print || true

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
