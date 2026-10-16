#!/usr/bin/env bash
# Manually executed only in an approved maintenance window.
# Never invoked by push, PR checks or the legacy deployment pipeline.
set -Eeuo pipefail

APP_DIR=/opt/aplussolution
GREEN_DIR=/opt/aplussolution-green
COMPOSE_FILE="$GREEN_DIR/compose.green.yml"
DOMAIN=app.aplus-solution.de
MIN_MEM_MB=1800
MIN_DISK_MB=6144
MODE="${1:-}"
ACK="${2:-}"
PROJECT=aplusgreen

fail() { echo "ABORT: $*" >&2; exit 1; }
info() { echo "INFO: $*"; }
require() { command -v "$1" >/dev/null || fail "Missing $1"; }
host_preflight() {
  require docker
  require curl
  require awk
  require flock
  test -f "$APP_DIR/.env" || fail "Production .env missing"
  test -f "$APP_DIR/Caddyfile" || fail "Production Caddyfile missing"
  docker info >/dev/null || fail "Docker daemon inaccessible"
  docker network inspect aplussolution_default >/dev/null || fail "Shared Docker network missing"
  docker volume inspect aplussolution_media_data >/dev/null || fail "Shared media volume missing"
  cd "$APP_DIR"
  for service in backend frontend caddy db redis; do
    cid="$(docker compose ps -q "$service")"
    test -n "$cid" || fail "Blue $service container missing"
    test "$(docker inspect -f '{{.State.Running}}' "$cid")" = true || fail "Blue $service not running"
  done
  curl -fsS --connect-timeout 3 --max-time 12 \
    --resolve "$DOMAIN:443:127.0.0.1" \
    "https://$DOMAIN/health/" | grep -q '"ok"' \
    || fail "Existing blue liveness is unhealthy, do not stage/switch"
  # Never build images on STRATO. Green needs free memory for two extra
  # short-lived web containers and disk for prebuilt image layers.
  local mem disk
  mem="$(awk '/^MemAvailable:/ {print int($2/1024)}' /proc/meminfo)"
  disk="$(df -Pm /var/lib/docker | awk 'END {print $4}')"
  info "Available RAM ${mem}MB; Docker disk ${disk}MB"
  [[ "$mem" =~ ^[0-9]+$ ]] && ((mem>=MIN_MEM_MB)) \
    || fail "Not enough available RAM for parallel green. Use another host."
  [[ "$disk" =~ ^[0-9]+$ ]] && ((disk>=MIN_DISK_MB)) \
    || fail "Not enough disk for green images. Use another host."
}

blue_caddy() {
  cd "$APP_DIR"
  docker compose ps -q caddy
}
green_compose() {
  test -s "$COMPOSE_FILE" || fail "Green compose file not staged"
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" "$@"
}
green_ready() {
  local cid
  cid="$(green_compose ps -q backend-green)"
  test -n "$cid" || fail "Green backend missing"
  test "$(docker inspect -f '{{.State.Health.Status}}' "$cid")" = healthy \
    || fail "Green backend not healthy"
  cid="$(green_compose ps -q frontend-green)"
  test -n "$cid" || fail "Green frontend missing"
  test "$(docker inspect -f '{{.State.Health.Status}}' "$cid")" = healthy \
    || fail "Green frontend not healthy"
  # Both probes run INSIDE the green backend. No public service, account,
  # client data, or database record is mutated by staging checks.
  green_compose exec -T backend-green python - <<'PY'
import json, urllib.request
backend='http://127.0.0.1:8000/api/status/ready/'
frontend='http://aplus-green-frontend:80/'
with urllib.request.urlopen(backend, timeout=10) as response:
    assert response.status == 200
    assert json.load(response)['status'] == 'ok'
with urllib.request.urlopen(frontend, timeout=10) as response:
    assert response.status == 200
    assert b'<div id="root"' in response.read(200000)
print('GREEN_BACKEND_DB_AND_FRONTEND_READY')
PY
  # No migrations may be pending: backend entrypoint is intentionally skipped.
  green_compose exec -T backend-green python manage.py migrate --check \
    || fail "Pending database migrations — cutover prohibited"
}
stage() {
  host_preflight
  test -f "$GREEN_DIR/images.env" || fail "Explicit pinned images.env required"
  # IMAGE pins must be immutable release digests. Never use :latest.
  set -a
  # shellcheck disable=SC1091
  source "$GREEN_DIR/images.env"
  set +a
  [[ "${BACKEND_IMAGE:-}" == *@sha256:* ]] || fail "backend must use immutable sha256 digest"
  [[ "${FRONTEND_IMAGE:-}" == *@sha256:* ]] || fail "frontend must use immutable sha256 digest"
  info "Downloading prebuilt green images only (no docker build)"
  green_compose pull backend-green frontend-green
  green_compose up -d --no-build --pull never backend-green frontend-green
  for attempt in $(seq 1 36); do
    if green_ready >/dev/null 2>&1; then
      green_ready
      info "Green ready; BLUE ROUTING IS UNCHANGED"
      return
    fi
    sleep 5
  done
  green_compose ps -a
  fail "Green never became ready. Existing production routing untouched."
}
prepare_caddy() {
  local cid="$1"
  local config="$GREEN_DIR/Caddyfile.green"
  sed -e 's/reverse_proxy backend:8000/reverse_proxy aplus-green-backend:8000/g' \
      -e 's/reverse_proxy frontend:80/reverse_proxy aplus-green-frontend:80/g' \
      "$APP_DIR/Caddyfile" > "$config"
  grep -q 'reverse_proxy aplus-green-backend:8000' "$config" || fail "Backend upstream not transformed"
  grep -q 'reverse_proxy aplus-green-frontend:80' "$config" || fail "Frontend upstream not transformed"
  docker cp "$config" "$cid:/tmp/aplus-green.Caddyfile"
  docker exec "$cid" caddy validate --config /tmp/aplus-green.Caddyfile --adapter caddyfile
}
reload_blue() {
  local cid="$1"
  info "Restoring original mounted Caddy config without restarting Caddy"
  docker exec "$cid" caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
}
cutover() {
  [[ "$ACK" == "I_APPROVE_CUTOVER" ]] || fail "Explicit I_APPROVE_CUTOVER confirmation required"
  host_preflight
  green_ready
  local cid
  cid="$(blue_caddy)"
  test -n "$cid" || fail "Running Caddy missing"
  prepare_caddy "$cid"
  info "Switching only Caddy runtime routing; keeping BLUE containers running"
  local switched=0
  rollback_on_error() {
    if ((switched==1)); then
      reload_blue "$cid" || true
      echo "AUTOMATIC_RUNTIME_ROLLBACK_ATTEMPTED" >&2
    fi
  }
  trap rollback_on_error ERR
  switched=1
  docker exec "$cid" caddy reload --config /tmp/aplus-green.Caddyfile --adapter caddyfile
  for i in $(seq 1 12); do
    curl -fsS --connect-timeout 3 --max-time 8 \
      --resolve "$DOMAIN:443:127.0.0.1" \
      "https://$DOMAIN/api/status/ready/?green_check=$i" \
      | grep -q '"status": "ok"' || fail "Green API readiness check $i failed"
    curl -fsS --connect-timeout 3 --max-time 8 \
      --resolve "$DOMAIN:443:127.0.0.1" \
      "https://$DOMAIN/?green_check=$i" \
      | grep -q '<div id="root"' || fail "Green HTML check $i failed"
    sleep 3
  done
  switched=0
  trap - ERR
  info "CUTOVER_HEALTHY: BLUE containers retained for rollback"
}
rollback() {
  [[ "$ACK" == "I_APPROVE_ROLLBACK" ]] || fail "Explicit I_APPROVE_ROLLBACK confirmation required"
  local cid
  cid="$(blue_caddy)"
  test -n "$cid" || fail "Cannot find the original Caddy container"
  reload_blue "$cid"
  curl -fsS --connect-timeout 3 --max-time 12 \
    --resolve "$DOMAIN:443:127.0.0.1" "https://$DOMAIN/health/" \
    | grep -q '"ok"' || fail "Original blue failed health check; investigate immediately"
  info "ROLLBACK_TO_BLUE_CONFIRMED; green containers left running for forensic analysis"
}
# A lock guards ONLY this manual blue-green workflow; legacy deploy must also
# remain DISABLED so it cannot stop/recreate Caddy during staged cutover.
exec 9>/var/lock/aplus-bluegreen.lock
flock -n 9 || fail "Another bluegreen process is active"
case "$MODE" in
  preflight) host_preflight; info 'PREFLIGHT_OK, no mutation' ;;
  stage) stage ;;
  cutover) cutover ;;
  rollback) rollback ;;
  *) fail "Usage: $0 preflight|stage|cutover I_APPROVE_CUTOVER|rollback I_APPROVE_ROLLBACK" ;;
esac
