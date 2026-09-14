#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

export APP_ENV=staging
export CAPACITOR_APP_ID="${CAPACITOR_APP_ID:-de.aplussolution.staging}"
export CAPACITOR_APP_NAME="${CAPACITOR_APP_NAME:-A+ Solution Staging}"
export VITE_APP_ENV=staging
export VITE_API_URL="${VITE_API_URL:-https://staging.app.aplus-solution.de/api}"

if [[ "$CAPACITOR_APP_ID" == "de.aplussolution.workforce" ]]; then
  echo "Refusing staging build with the production Android package." >&2
  exit 1
fi

case "$VITE_API_URL" in
  https://app.aplus-solution.de/api|https://solution.smarbiz.sbs/api)
    echo "Refusing staging build against the production API: $VITE_API_URL" >&2
    exit 1
    ;;
esac

echo "Building Android staging app ${CAPACITOR_APP_ID} against ${VITE_API_URL}."
bash "$SCRIPT_DIR/build-publisher-android.sh"
