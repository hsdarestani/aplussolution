#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FRONTEND="$ROOT/frontend"
cd "$FRONTEND"

: "${ANDROID_KEYSTORE_PATH:?Publisher must provide ANDROID_KEYSTORE_PATH}"
: "${ANDROID_KEYSTORE_PASSWORD:?Publisher must provide ANDROID_KEYSTORE_PASSWORD}"
: "${ANDROID_KEY_ALIAS:?Publisher must provide ANDROID_KEY_ALIAS}"
: "${ANDROID_KEY_PASSWORD:?Publisher must provide ANDROID_KEY_PASSWORD}"
: "${APP_VERSION_NAME:?Publisher must provide APP_VERSION_NAME}"
: "${APP_BUILD_NUMBER:?Publisher must provide APP_BUILD_NUMBER}"

npm install --no-audit --no-fund
npm run build
rm -rf android
npx cap add android
npx cap sync android
node scripts/prepare-native.mjs android

cp "$ANDROID_KEYSTORE_PATH" android/app/aplus-release.jks
chmod 600 android/app/aplus-release.jks

python3 scripts/patch-android-gradle.py

cd android
./gradlew bundleRelease

test -n "$(find app/build/outputs/bundle/release -maxdepth 1 -name '*.aab' -print -quit)"
echo "Publisher Android AAB created successfully for ${APP_VERSION_NAME} (${APP_BUILD_NUMBER})."
