#!/usr/bin/env bash
# One-time Django Admin backend-only release with fail-closed guards and rollback.
set -Eeuo pipefail
cd /opt/aplussolution
: "$RELEASE_ID" "$BACKEND_IMAGE"
[[ "$RELEASE_ID" =~ ^[0-9]+$ ]] || exit 2
[[ "$BACKEND_IMAGE" == *@sha256:* ]] || exit 2
[[ "$1" == release ]] || exit 2
exec 9>/var/lock/aplus-singlehost-release.lock
flock -n 9 || { echo "ABORT_RELEASE_LOCK"; exit 2; }
test -s .env && test -s docker-compose.override.yml
# Only one backend container is replaced; all other containers stay running.
mem="$(awk '/^MemAvailable:/ {print int($2/1024)}' /proc/meminfo)"
disk="$(df -Pm /var/lib/docker | awk 'END{print $4}')"
echo "BACKEND_ONLY_AVAILABLE_RAM_MB=$mem DISK_MB=$disk"
(( mem >= 650 && disk >= 3000 )) || { echo "ABORT_INSUFFICIENT_RESOURCES"; exit 2; }
for svc in db redis backend frontend caddy celery celery-beat; do
  cid="$(docker compose ps -q "$svc")"
  test -n "$cid" && test "$(docker inspect -f '{{.State.Running}}' "$cid")" = true || { echo "ABORT_UNHEALTHY_SERVICE=$svc"; exit 2; }
done
curl -fsS --max-time 15 --resolve app.aplus-solution.de:443:127.0.0.1 https://app.aplus-solution.de/api/status/ready/ -o /tmp/aplus-admin-backend-before.json
grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"' /tmp/aplus-admin-backend-before.json
docker image inspect "$BACKEND_IMAGE" >/dev/null
archive="/opt/aplus-release-$RELEASE_ID"
mkdir -p -m 700 "$archive"
cp -p docker-compose.override.yml "$archive/old-production-override.yml"
old_image_id="$(docker inspect -f '{{.Image}}' "$(docker compose ps -q backend)")"
old_image_tag="aplus-saved-backend:$RELEASE_ID"
docker tag "$old_image_id" "$old_image_tag"
cat > "$archive/rollback.yml" <<EOF
services:
  backend:
    image: "$old_image_tag"
EOF
# Make a minimal backend image edit; never rewrite unrelated override entries.
python3 - "$BACKEND_IMAGE" "$archive/new-production-override.yml" <<'PY'
import pathlib, re, sys
pin, dest = sys.argv[1:]
source = pathlib.Path("docker-compose.override.yml").read_text()
lines = source.splitlines(keepends=True)
starts = [i for i, line in enumerate(lines) if re.fullmatch(r"  backend:\s*\n?", line)]
if len(starts) != 1:
    raise SystemExit("ABORT_AMBIGUOUS_BACKEND_OVERRIDE")
start = starts[0]
end = next((i for i in range(start + 1, len(lines)) if re.match(r"^  [A-Za-z0-9_-]+:\s*$", lines[i])), len(lines))
images = [i for i in range(start + 1, end) if re.match(r"^    image:\s*.*$", lines[i])]
if len(images) != 1:
    raise SystemExit("ABORT_BACKEND_IMAGE_ENTRY_NOT_UNIQUE")
lines[images[0]] = "    image: " + pin + "\n"
pathlib.Path(dest).write_text("".join(lines))
PY
# The effective config must differ in backend.image ONLY.
python3 - "$archive/new-production-override.yml" "$BACKEND_IMAGE" <<'PY'
import json, subprocess, sys
new_path, pin = sys.argv[1:]
def effective(path):
    output = subprocess.check_output(["docker", "compose", "-f", "docker-compose.yml", "-f", path, "config", "--format", "json"], stderr=subprocess.DEVNULL)
    return json.loads(output)["services"]
old = effective("docker-compose.override.yml")
new = effective(new_path)
if old.keys() != new.keys() or new["backend"].get("image") != pin:
    raise SystemExit("ABORT_COMPOSE_STRUCTURE_MISMATCH")
for name in old:
    before, after = dict(old[name]), dict(new[name])
    if name == "backend":
        before.pop("image", None)
        after.pop("image", None)
    if before != after:
        raise SystemExit("ABORT_UNRELATED_CONFIG_DRIFT_" + name)
print("BACKEND_IMAGE_ONLY_CHANGE_CONFIRMED")
PY
switched=0
completed=0
rollback() {
  status=$?
  if (( switched == 1 && completed == 0 )); then
    echo "BACKEND_ONLY_ROLLBACK_START exit=$status"
    install -m 600 "$archive/old-production-override.yml" /opt/aplussolution/docker-compose.override.yml
    timeout 200 docker compose -f docker-compose.yml -f "$archive/old-production-override.yml" -f "$archive/rollback.yml" up -d --no-deps --no-build --pull never backend || true
    echo "BACKEND_ONLY_ROLLBACK_ATTEMPTED"
  fi
}
trap rollback EXIT
switched=1
timeout 200 docker compose -f docker-compose.yml -f "$archive/new-production-override.yml" up -d --no-deps --no-build --pull never backend
ready=0
for i in $(seq 1 35); do
  if curl -fsS --connect-timeout 3 --max-time 10 --resolve app.aplus-solution.de:443:127.0.0.1 https://app.aplus-solution.de/api/status/ready/ -o "$archive/readiness.json" 2>/dev/null &&
     grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"' "$archive/readiness.json"; then
    ready=1
    break
  fi
  sleep 3
done
(( ready == 1 )) || { echo "ABORT_NEW_BACKEND_UNHEALTHY"; exit 3; }
docker compose -f docker-compose.yml -f "$archive/new-production-override.yml" exec -T backend python manage.py check </dev/null
for svc in db redis frontend caddy celery celery-beat; do
  cid="$(docker compose ps -q "$svc")"
  test -n "$cid" && test "$(docker inspect -f '{{.State.Running}}' "$cid")" = true || { echo "ABORT_OTHER_SERVICE_CHANGED_$svc"; exit 3; }
done
install -m 600 "$archive/new-production-override.yml" docker-compose.override.yml
completed=1
trap - EXIT
echo "BACKEND_ONLY_RELEASE_SUCCESS"
