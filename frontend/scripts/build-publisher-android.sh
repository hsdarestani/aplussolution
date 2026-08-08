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

python3 - <<'PY'
import os
import re
from pathlib import Path

path = Path("android/app/build.gradle")
text = path.read_text()
version_name = os.environ["APP_VERSION_NAME"]
build_number = int(os.environ["APP_BUILD_NUMBER"])

if "signingConfigs {" not in text:
    text = text.replace(
        "android {",
        '''android {
    signingConfigs {
        release {
            storeFile file("aplus-release.jks")
            storePassword System.getenv("ANDROID_KEYSTORE_PASSWORD")
            keyAlias System.getenv("ANDROID_KEY_ALIAS")
            keyPassword System.getenv("ANDROID_KEY_PASSWORD")
        }
    }
''',
        1,
    )

if "signingConfig signingConfigs.release" not in text:
    marker = "release {"
    if marker not in text:
        raise SystemExit("Could not find the Android release build type.")
    text = text.replace(marker, "release {\n            signingConfig signingConfigs.release", 1)

text, version_code_count = re.subn(
    r"\bversionCode\s+\d+",
    f"versionCode {build_number}",
    text,
    count=1,
)
text, version_name_count = re.subn(
    r'\bversionName\s+["\'][^"\']+["\']',
    f'versionName "{version_name}"',
    text,
    count=1,
)
if version_code_count != 1 or version_name_count != 1:
    raise SystemExit("Could not set Android versionCode/versionName from Publisher release metadata.")

path.write_text(text)
PY

cd android
./gradlew bundleRelease

test -n "$(find app/build/outputs/bundle/release -maxdepth 1 -name '*.aab' -print -quit)"
echo "Publisher Android AAB created successfully for ${APP_VERSION_NAME} (${APP_BUILD_NUMBER})."
