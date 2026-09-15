#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

export APP_ENV=staging
export CAPACITOR_APP_ID="${CAPACITOR_APP_ID:-de.aplussolution.staging}"
export CAPACITOR_APP_NAME="${CAPACITOR_APP_NAME:-A+ Solution Staging}"
export VITE_APP_ENV=staging
export VITE_NATIVE_APP_ID="${VITE_NATIVE_APP_ID:-de.aplussolution.staging}"
export VITE_API_URL="${VITE_API_URL:-https://staging.app.aplus-solution.de/api}"
export REQUIRE_NATIVE_PUSH="${REQUIRE_NATIVE_PUSH:-1}"

if [[ "$CAPACITOR_APP_ID" == "de.aplussolution.workforce" ]]; then
  echo "Refusing staging build with the production Android package." >&2
  exit 1
fi

if [[ "$VITE_NATIVE_APP_ID" != "$CAPACITOR_APP_ID" ]]; then
  echo "Refusing staging build with mismatched VITE_NATIVE_APP_ID=$VITE_NATIVE_APP_ID." >&2
  exit 1
fi

case "$VITE_API_URL" in
  https://app.aplus-solution.de/api|https://solution.smarbiz.sbs/api)
    echo "Refusing staging build against the production API: $VITE_API_URL" >&2
    exit 1
    ;;
esac

# The Firebase project/API key is already checked into the production client config.
# For staging, derive a single staging client at build time so no new secret is added
# to Git history while still using the exact Firebase app that belongs to
# de.aplussolution.staging.
if [[ -z "${GOOGLE_SERVICES_JSON_BASE64:-}" && -z "${GOOGLE_SERVICES_JSON:-}" ]]; then
  FIREBASE_SOURCE="$SCRIPT_DIR/../firebase/google-services.json"
  if [[ ! -f "$FIREBASE_SOURCE" ]]; then
    echo "Missing Firebase source config: $FIREBASE_SOURCE" >&2
    exit 1
  fi
  export GOOGLE_SERVICES_JSON="$(node - "$FIREBASE_SOURCE" <<'NODE'
const fs = require('fs');
const source = process.argv[2];
const config = JSON.parse(fs.readFileSync(source, 'utf8'));
const template = (config.client || []).find(
  (client) => client?.client_info?.android_client_info?.package_name === 'de.aplussolution.workforce',
) || (config.client || [])[0];
if (!template) throw new Error('Firebase source config has no Android client.');
const stagingClient = JSON.parse(JSON.stringify(template));
stagingClient.client_info.mobilesdk_app_id = '1:556347591130:android:aa39dc4d676c8c33b918e3';
stagingClient.client_info.android_client_info.package_name = 'de.aplussolution.staging';
config.client = [stagingClient];
process.stdout.write(JSON.stringify(config));
NODE
)"
fi

echo "Building push-ready Android staging app ${CAPACITOR_APP_ID} against ${VITE_API_URL}."
bash "$SCRIPT_DIR/build-publisher-android.sh"
