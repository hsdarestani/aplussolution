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

export REQUIRE_NATIVE_PUSH=1

npm install --no-audit --no-fund
npm run build
rm -rf android
npx cap add android
npx cap sync android
node scripts/prepare-native.mjs android

# Assert the exact notification branding before Gradle compiles resources.
test -f android/app/src/main/res/drawable/ic_stat_aplus.xml
test -f android/app/src/main/res/raw/solution_signature.wav
grep -Fq 'M2.2,20 L6.6,4' android/app/src/main/res/drawable/ic_stat_aplus.xml
grep -Fq 'com.google.firebase.messaging.default_notification_icon' android/app/src/main/AndroidManifest.xml
grep -Fq 'aplus_updates_signature_v1' android/app/src/main/AndroidManifest.xml

cp "$ANDROID_KEYSTORE_PATH" android/app/aplus-release.jks
chmod 600 android/app/aplus-release.jks
python3 scripts/patch-android-gradle.py

cd android
./gradlew assembleRelease

APK="$(find app/build/outputs/apk/release -maxdepth 1 -name '*.apk' -print -quit)"
test -n "$APK"
test -s "$APK"

# Inspect the compiled Android resource table rather than ZIP paths: aapt may
# rewrite resource paths during packaging and pipefail can turn grep -q into a
# false failure when an upstream command receives SIGPIPE.
BUILD_TOOLS="$(ls "$ANDROID_HOME/build-tools" | sort -V | tail -n1)"
AAPT="$ANDROID_HOME/build-tools/$BUILD_TOOLS/aapt"
"$AAPT" dump resources "$APK" > /tmp/aplus-notification-resources.txt
grep -Fq 'ic_stat_aplus' /tmp/aplus-notification-resources.txt
grep -Fq 'solution_signature' /tmp/aplus-notification-resources.txt

echo "Publisher Android smoke APK created and notification branding verified for ${APP_VERSION_NAME} (${APP_BUILD_NUMBER})."
