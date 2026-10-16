#!/usr/bin/env bash
# Single-host prebuilt image switch. User approved controlled brief interruption.
set -Eeuo pipefail
cd /opt/aplussolution
: "${RELEASE_ID:?}" "${BACKEND_IMAGE:?}" "${FRONTEND_IMAGE:?}"
[[ "$1" == release ]] || exit 2
[[ "$RELEASE_ID" =~ ^[0-9]+$ ]] || exit 2
[[ "$BACKEND_IMAGE" == *@sha256:* && "$FRONTEND_IMAGE" == *@sha256:* ]] || exit 2
exec 9>/var/lock/aplus-singlehost-release.lock
flock -n 9 || { echo "ABORT: release lock held"; exit 2; }
test ! -e docker-compose.override.yml || { echo "ABORT: compose override already exists"; exit 2; }
for svc in db redis backend frontend caddy celery celery-beat; do
  cid="$(timeout 12 docker compose ps -q "$svc")"
  test -n "$cid" && test "$(docker inspect -f '{{.State.Running}}' "$cid")" = true || { echo "ABORT: $svc down"; exit 2; }
done
curl -fsS --connect-timeout 3 --max-time 12 --resolve app.aplus-solution.de:443:127.0.0.1 https://app.aplus-solution.de/health/ | grep -q '"ok"' || { echo "ABORT: origin not healthy"; exit 2; }
ram="$(awk '/^MemAvailable:/ {print int($2/1024)}' /proc/meminfo)"
disk="$(df -Pm /var/lib/docker | awk 'END{print $4}')"
echo "PRECHECK_AVAILABLE_RAM_MB=$ram DISK_MB=$disk"
(( ram >= 850 && disk >= 2500 )) || { echo "ABORT: resources too low"; exit 2; }
docker image inspect "$BACKEND_IMAGE" "$FRONTEND_IMAGE" >/dev/null || { echo "ABORT: images not pre-pulled"; exit 2; }
old_backend_id="$(docker inspect -f '{{.Image}}' "$(docker compose ps -q backend)")"
old_frontend_id="$(docker inspect -f '{{.Image}}' "$(docker compose ps -q frontend)")"
old_backend="aplus-saved-backend:$RELEASE_ID"
old_frontend="aplus-saved-frontend:$RELEASE_ID"
docker tag "$old_backend_id" "$old_backend"
docker tag "$old_frontend_id" "$old_frontend"
archive="/opt/aplus-release-$RELEASE_ID"
mkdir -m 700 -p "$archive"
new="$archive/new-compose.yml"
old="$archive/old-compose.yml"
cat > "$new" <<EOF
services:
  backend:
    image: "$BACKEND_IMAGE"
    command: ["gunicorn","config.wsgi:application","--bind","0.0.0.0:8000","--workers","3","--timeout","120"]
  frontend:
    image: "$FRONTEND_IMAGE"
EOF
cat > "$old" <<EOF
services:
  backend:
    image: "$old_backend"
    command: ["gunicorn","config.wsgi:application","--bind","0.0.0.0:8000","--workers","3","--timeout","120"]
  frontend:
    image: "$old_frontend"
EOF
chmod 600 "$new" "$old"
docker compose -f docker-compose.yml -f "$new" config --quiet
docker compose -f docker-compose.yml -f "$old" config --quiet
switched=0
completed=0
rollback() {
  code=$?
  if (( switched == 1 && completed == 0 )); then
    echo "AUTOMATIC_ROLLBACK_TRIGGERED exit=$code"
    timeout 240 docker compose -f docker-compose.yml -f "$old" up -d --no-deps --no-build --pull never backend frontend || true
    docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1 || true
    for i in $(seq 1 25); do
      if curl -fsS --connect-timeout 3 --max-time 7 --resolve app.aplus-solution.de:443:127.0.0.1 https://app.aplus-solution.de/health/ | grep -q '"ok"'; then
        echo "AUTOMATIC_ROLLBACK_HEALTHY"
        break
      fi
      sleep 3
    done
  fi
}
trap rollback EXIT
echo "START_CUTOVER_UTC=$(date -u +%FT%TZ)"
switched=1
timeout 240 docker compose -f docker-compose.yml -f "$new" up -d --no-deps --no-build --pull never backend frontend
ready=0
for i in $(seq 1 40); do
  api_ok=0
  web_ok=0
  if curl -fsS --connect-timeout 3 --max-time 8 --resolve app.aplus-solution.de:443:127.0.0.1 "https://app.aplus-solution.de/api/status/ready/?release=$RELEASE_ID" | grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"'; then api_ok=1; fi
  if curl -fsS --connect-timeout 3 --max-time 8 --resolve app.aplus-solution.de:443:127.0.0.1 "https://app.aplus-solution.de/maintenance.html?release=$RELEASE_ID" | grep -q 'A+ SOLUTION'; then web_ok=1; fi
  if (( api_ok == 1 && web_ok == 1 )); then ready=1; echo "NEW_APP_READY iteration=$i"; break; fi
  if (( i == 15 )); then
    docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1 || true
  fi
  sleep 3
done
(( ready == 1 )) || { echo "NEW_APP_HEALTH_CHECK_FAILED"; exit 3; }
for svc in db redis caddy celery celery-beat; do
  cid="$(docker compose ps -q "$svc")"
  test -n "$cid" && test "$(docker inspect -f '{{.State.Running}}' "$cid")" == true || exit 3
done
curl -fsS --connect-timeout 3 --max-time 12 --resolve app.aplus-solution.de:443:127.0.0.1 https://app.aplus-solution.de/ | grep -q '<div id="root"'
install -m 600 "$new" /opt/aplussolution/docker-compose.override.yml
echo "RELEASE_SUCCESS_UTC=$(date -u +%FT%TZ)"
completed=1
trap - EXIT
