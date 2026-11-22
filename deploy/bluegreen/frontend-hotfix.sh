#!/usr/bin/env bash
# Low-RAM frontend-only release: no container stop, restart or new stack.
set -Eeuo pipefail
: "${RELEASE_SHA:?Missing commit}"
: "${INDEX_SHA256:?Missing expected index checksum}"
[[ "$RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]] || exit 2
[[ "$INDEX_SHA256" =~ ^[0-9a-f]{64}$ ]] || exit 2

root=/usr/share/nginx/html
archive="/tmp/aplus-frontend-$RELEASE_SHA.tar.gz"
base="/opt/aplussolution-frontend-releases/$RELEASE_SHA"
staging="$base/new"
backup="$base/previous"
mkdir -p "$staging" "$backup"
exec 8>/var/lock/aplus-frontend-hotfix.lock
flock -n 8 || { echo 'Concurrent frontend release blocked' >&2; exit 1; }

test -s "$archive"
cd /opt/aplussolution
cid="$(docker compose ps -q frontend)"
test -n "$cid"
test "$(docker inspect -f '{{.State.Running}}' "$cid")" = true
docker exec "$cid" test -w "$root"
docker exec "$cid" test -f "$root/index.html"
curl -fsS --connect-timeout 3 --max-time 12 \
  --resolve app.aplus-solution.de:443:127.0.0.1 \
  https://app.aplus-solution.de/health/ | grep -q '"ok"'

tar -xzf "$archive" -C "$staging"
test -s "$staging/index.html"
test -d "$staging/assets"
test "$(sha256sum "$staging/index.html" | awk '{print $1}')" = "$INDEX_SHA256"

# Keep the complete old static tree to restore if any post-swap probe fails.
docker cp "$cid:$root/." "$backup/"
test -s "$backup/index.html"
docker exec "$cid" mkdir -p "$root/.next-$RELEASE_SHA"
docker cp "$staging/." "$cid:$root/.next-$RELEASE_SHA/"
patched=0
rollback_if_needed() {
  code=$?
  if [ "$patched" = 1 ]; then
    echo "Hotfix failed ($code); restoring the former static files" >&2
    docker cp "$backup/." "$cid:$root/" || true
  fi
}
trap rollback_if_needed EXIT
patched=1

docker exec -i "$cid" sh -s -- "$RELEASE_SHA" <<'CONTAINER_SCRIPT'
set -eu
revision="$1"
root=/usr/share/nginx/html
next="$root/.next-$revision"
cd "$next"
# Install hashed assets first, preserve assets still needed by older sessions.
find . -type f ! -name index.html ! -name sw.js \
  ! -name registerSW.js ! -name manifest.webmanifest | while IFS= read -r rel; do
    mkdir -p "$root/$(dirname "$rel")"
    cp "$rel" "$root/$rel"
  done
for rel in registerSW.js manifest.webmanifest sw.js; do
  if [ -f "$rel" ]; then
    cp "$rel" "$root/$rel.next"
    mv "$root/$rel.next" "$root/$rel"
  fi
done
cp index.html "$root/index.html.next"
mv "$root/index.html.next" "$root/index.html"
CONTAINER_SCRIPT

actual="$(docker exec "$cid" sha256sum "$root/index.html" | awk '{print $1}')"
test "$actual" = "$INDEX_SHA256"
served="$(curl -fsS --connect-timeout 3 --max-time 12 \
  --resolve app.aplus-solution.de:443:127.0.0.1 \
  "https://app.aplus-solution.de/?hours_release=$RELEASE_SHA" | sha256sum | awk '{print $1}')"
test "$served" = "$INDEX_SHA256"
curl -fsS --connect-timeout 3 --max-time 12 \
  --resolve app.aplus-solution.de:443:127.0.0.1 \
  https://app.aplus-solution.de/health/ | grep -q '"ok"'
printf '%s\n' "$RELEASE_SHA" > "$base/applied_revision.txt"
patched=0
trap - EXIT
docker exec "$cid" rm -rf "$root/.next-$RELEASE_SHA"
echo "FRONTEND_HOTFIX_VERIFIED commit=$RELEASE_SHA index_sha256=$INDEX_SHA256"
