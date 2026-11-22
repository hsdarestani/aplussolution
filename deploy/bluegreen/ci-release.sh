#!/usr/bin/env bash
# One-shot approved GitHub Actions release helper on the STRATO primary.
# Calls the existing guarded blue-green script; never stops blue containers.
set -Eeuo pipefail

: "${BACKEND_DIGEST:?Missing backend digest}"
: "${FRONTEND_DIGEST:?Missing frontend digest}"
: "${IMAGE_OWNER:?Missing image owner}"
: "${GHCR_USER:?Missing GHCR user}"
[[ "$BACKEND_DIGEST" =~ ^sha256:[a-f0-9]{64}$ ]] || { echo 'Invalid backend digest' >&2; exit 1; }
[[ "$FRONTEND_DIGEST" =~ ^sha256:[a-f0-9]{64}$ ]] || { echo 'Invalid frontend digest' >&2; exit 1; }
[[ "$IMAGE_OWNER" =~ ^[a-zA-Z0-9_-]+$ ]] || { echo 'Invalid owner' >&2; exit 1; }
[[ "$GHCR_USER" =~ ^[a-zA-Z0-9_-]+$ ]] || { echo 'Invalid user' >&2; exit 1; }

exec 8>/var/lock/aplus-ci-release.lock
flock -n 8 || { echo 'Another release is running' >&2; exit 1; }
install -d -m 700 /opt/aplussolution-green
install -m 700 /tmp/aplus-ci-release.sh /opt/aplussolution-green/release.sh
install -m 600 /tmp/aplus-ci-compose.green.yml /opt/aplussolution-green/compose.green.yml
printf 'BACKEND_IMAGE=ghcr.io/%s/aplus-bluegreen-backend@%s\nFRONTEND_IMAGE=ghcr.io/%s/aplus-bluegreen-frontend@%s\n'   "$IMAGE_OWNER" "$BACKEND_DIGEST" "$IMAGE_OWNER" "$FRONTEND_DIGEST"   > /opt/aplussolution-green/images.env
chmod 600 /opt/aplussolution-green/images.env

auth_dir="$(mktemp -d /tmp/aplus-ghcr-auth.XXXXXX)"
export DOCKER_CONFIG="$auth_dir"
trap 'rm -rf "$auth_dir"' EXIT
# Short-lived GitHub token is supplied through encrypted SSH stdin only.
docker login ghcr.io --username "$GHCR_USER" --password-stdin
/opt/aplussolution-green/release.sh preflight
/opt/aplussolution-green/release.sh stage
/opt/aplussolution-green/release.sh cutover I_APPROVE_CUTOVER
echo "APPLUS_SAFE_CUTOVER_COMPLETE"
