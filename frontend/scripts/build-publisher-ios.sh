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

ARCHIVE_PATH="$FRONTEND/ios/build/APlusWorkforce.xcarchive"
EXPORT_PATH="$FRONTEND/ios/build/export"
EXPORT_OPTIONS="$FRONTEND/ios/ExportOptions.plist"
mkdir -p "$EXPORT_PATH"

# Publisher installs a short-lived Apple Distribution certificate/private key
# in an ephemeral keychain and installs the matching App Store provisioning
# profile before invoking this script. Use those exact assets instead of
# Automatic signing, which otherwise asks Apple for a Development profile and
# registered test device even though this is an App Store archive.
xcodebuild \
  -workspace ios/App/App.xcworkspace \
  -scheme App \
  -configuration Release \
  -destination 'generic/platform=iOS' \
  -archivePath "$ARCHIVE_PATH" \
  DEVELOPMENT_TEAM="$IOS_TEAM_ID" \
  PRODUCT_BUNDLE_IDENTIFIER="$IOS_BUNDLE_ID" \
  CODE_SIGN_STYLE=Manual \
  CODE_SIGN_IDENTITY="$IOS_CODE_SIGN_IDENTITY" \
  PROVISIONING_PROFILE_SPECIFIER="$IOS_PROVISIONING_PROFILE_SPECIFIER" \
  OTHER_CODE_SIGN_FLAGS="--keychain $IOS_SIGNING_KEYCHAIN" \
  MARKETING_VERSION="$APP_VERSION_NAME" \
  CURRENT_PROJECT_VERSION="$APP_BUILD_NUMBER" \
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
