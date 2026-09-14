#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

: "${IOS_BUNDLE_ID:?Publisher must provide the staging IOS_BUNDLE_ID}"

export APP_ENV=staging
export CAPACITOR_APP_ID="${CAPACITOR_APP_ID:-$IOS_BUNDLE_ID}"
export CAPACITOR_APP_NAME="${CAPACITOR_APP_NAME:-A+ Solution Staging}"
export VITE_APP_ENV=staging
export VITE_API_URL="${VITE_API_URL:-https://staging.app.aplus-solution.de/api}"

if [[ "$IOS_BUNDLE_ID" != "de.aplussolution.staging" ]]; then
  echo "Refusing staging iOS build: expected IOS_BUNDLE_ID=de.aplussolution.staging, got $IOS_BUNDLE_ID" >&2
  exit 1
fi

if [[ "$CAPACITOR_APP_ID" != "$IOS_BUNDLE_ID" ]]; then
  echo "Capacitor app ID and iOS signing bundle ID must match." >&2
  exit 1
fi

case "$VITE_API_URL" in
  https://app.aplus-solution.de/api|https://solution.smarbiz.sbs/api)
    echo "Refusing staging build against the production API: $VITE_API_URL" >&2
    exit 1
    ;;
esac

echo "Building iOS staging app ${IOS_BUNDLE_ID} against ${VITE_API_URL}."
bash "$SCRIPT_DIR/build-publisher-ios.sh"
