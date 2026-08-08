#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FRONTEND="$ROOT/frontend"
cd "$FRONTEND"

: "${APPLE_API_KEY_PATH:?Publisher must provide APPLE_API_KEY_PATH}"
: "${APPLE_KEY_ID:?Publisher must provide APPLE_KEY_ID}"
: "${APPLE_ISSUER_ID:?Publisher must provide APPLE_ISSUER_ID}"
: "${IOS_TEAM_ID:?Publisher must provide IOS_TEAM_ID}"
: "${IOS_BUNDLE_ID:?Publisher must provide IOS_BUNDLE_ID}"
: "${APP_VERSION_NAME:?Publisher must provide APP_VERSION_NAME}"
: "${APP_BUILD_NUMBER:?Publisher must provide APP_BUILD_NUMBER}"

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

AUTH_ARGS=(
  -allowProvisioningUpdates
  -authenticationKeyPath "$APPLE_API_KEY_PATH"
  -authenticationKeyID "$APPLE_KEY_ID"
  -authenticationKeyIssuerID "$APPLE_ISSUER_ID"
)

xcodebuild \
  -workspace ios/App/App.xcworkspace \
  -scheme App \
  -configuration Release \
  -destination 'generic/platform=iOS' \
  -archivePath "$ARCHIVE_PATH" \
  "${AUTH_ARGS[@]}" \
  DEVELOPMENT_TEAM="$IOS_TEAM_ID" \
  PRODUCT_BUNDLE_IDENTIFIER="$IOS_BUNDLE_ID" \
  CODE_SIGN_STYLE=Automatic \
  MARKETING_VERSION="$APP_VERSION_NAME" \
  CURRENT_PROJECT_VERSION="$APP_BUILD_NUMBER" \
  archive

cat > "$EXPORT_OPTIONS" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>method</key><string>app-store-connect</string>
  <key>signingStyle</key><string>automatic</string>
  <key>teamID</key><string>${IOS_TEAM_ID}</string>
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
  -exportOptionsPlist "$EXPORT_OPTIONS" \
  "${AUTH_ARGS[@]}"

test -n "$(find "$EXPORT_PATH" -maxdepth 1 -name '*.ipa' -print -quit)"
echo "Publisher iOS IPA created successfully."
