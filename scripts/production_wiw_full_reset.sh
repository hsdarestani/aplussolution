#!/usr/bin/env bash
set -Eeuo pipefail

cd /opt/aplussolution

# v2 reruns the clean import once with bounded WIW history windows. The v1
# marker is intentionally not reused because the first broad-range reconciliation
# exposed a silent-empty /shifts response from WIW.
DONE_MARKER="/root/.aplussolution-wiw-full-reset-bounded-v2-20260821.done"
BACKUP_DIR="/root/aplussolution-backups"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DB_BACKUP="$BACKUP_DIR/pre-wiw-full-reset-$STAMP.sql.gz"
DB_CHECKSUM="$DB_BACKUP.sha256"
REPORT_FILE="$BACKUP_DIR/wiw-final-report-$STAMP.log"
COUNTS_BEFORE="$BACKUP_DIR/pre-wiw-counts-$STAMP.log"
COUNTS_AFTER="$BACKUP_DIR/post-wiw-counts-$STAMP.log"

apply_schedule_worker_config() {
  echo "Applying approved Dienstplan worker groups and visibility..."
  docker compose exec -T backend python manage.py configure_schedule_workers
}

run_mobile_shift_probe() {
  echo "Running rollback-only production mobile shift CRUD probe..."
  docker compose exec -T backend python manage.py diagnose_mobile_shift_crud
}

if [[ -f "$DONE_MARKER" ]]; then
  echo "WIW bounded full reset already completed; marker: $DONE_MARKER"
  cat "$DONE_MARKER"
  # Reapply the business-owned worker configuration on every deployment. This
  # keeps WIW refreshes from reintroducing removed workforce rows or resetting
  # Dienstplan group/client visibility.
  apply_schedule_worker_config
  # Even after the destructive one-time migration is retired, every release
  # should prove the exact mobile create/edit/assign paths against current
  # production-shaped WIW data. The command wraps every write in a rollback.
  run_mobile_shift_probe
  exit 0
fi

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

DB_USER="$(docker compose exec -T db printenv POSTGRES_USER | tr -d '\r')"
DB_NAME="$(docker compose exec -T db printenv POSTGRES_DB | tr -d '\r')"
: "${DB_USER:?POSTGRES_USER missing}"
: "${DB_NAME:?POSTGRES_DB missing}"

wait_backend() {
  local ready=0
  for _ in $(seq 1 90); do
    if docker compose exec -T backend curl -fsS http://127.0.0.1:8000/health/ >/dev/null 2>&1; then
      ready=1
      break
    fi
    sleep 4
  done
  [[ "$ready" -eq 1 ]]
}

reset_database() {
  docker compose exec -T db psql -U "$DB_USER" -d postgres -v ON_ERROR_STOP=1 \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();" >/dev/null
  docker compose exec -T db dropdb -U "$DB_USER" --if-exists "$DB_NAME"
  docker compose exec -T db createdb -U "$DB_USER" "$DB_NAME"
}

restore_database() {
  echo "Restoring pre-reset production database from $DB_BACKUP" >&2
  docker compose stop backend celery celery-beat >/dev/null 2>&1 || true
  reset_database
  gzip -dc "$DB_BACKUP" | docker compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 >/dev/null
  docker compose up -d backend >/dev/null
  if ! wait_backend; then
    echo "Rollback database restored, but backend did not become healthy." >&2
    docker compose logs --no-color --tail=250 backend >&2 || true
    return 1
  fi
  docker compose up -d celery celery-beat >/dev/null
  echo "Rollback completed successfully." >&2
}

# Non-destructive credential/API preflight. The final import performs its own
# complete 2000-01-01..2100-01-01 bounded snapshot fetch after the clean DB boots.
docker compose exec -T backend python manage.py shell -c "from core.wiw import WhenIWorkClient; c=WhenIWorkClient(); checks={};
for r in ('users','positions','locations','sites','shifts','times','availabilities','requests'):
    checks[r]=len(c.collection(r, params={'limit': 1}, optional=False).items)
print('WIW preflight OK', checks)"

docker compose exec -T backend python manage.py shell -c "from core.models import User,WorkerProfile,ClientCompany,Location,Position,Shift,TimeEntry,Availability,TimeOffRequest; print({'users':User.objects.count(),'workers':WorkerProfile.objects.count(),'clients':ClientCompany.objects.count(),'locations':Location.objects.count(),'positions':Position.objects.count(),'shifts':Shift.objects.count(),'times':TimeEntry.objects.count(),'availabilities':Availability.objects.count(),'requests':TimeOffRequest.objects.count()})" | tee "$COUNTS_BEFORE"

# Full SQL backup is the rollback boundary. Nothing destructive happens before this succeeds.
docker compose exec -T db pg_dump -U "$DB_USER" -d "$DB_NAME" | gzip -9 > "$DB_BACKUP"
test -s "$DB_BACKUP"
sha256sum "$DB_BACKUP" > "$DB_CHECKSUM"
chmod 600 "$DB_BACKUP" "$DB_CHECKSUM" "$COUNTS_BEFORE"
echo "Production backup ready: $DB_BACKUP"

perform_clean_import() {
  docker compose stop backend celery celery-beat >/dev/null || return 1
  reset_database || return 1
  docker compose exec -T redis redis-cli FLUSHALL >/dev/null || return 1

  docker compose up -d backend >/dev/null || return 1
  wait_backend || {
    docker compose logs --no-color --tail=250 backend >&2 || true
    return 1
  }

  # Dynamic WIW resources are proactively split into bounded windows and a
  # current/default probe must be contained in the resulting history snapshot.
  docker compose exec -T backend python manage.py migrate_wiw_final --apply --strict --compact | tee "$REPORT_FILE" || return 1

  docker compose exec -T backend python manage.py shell -c "from core.models import IntegrationSyncRun; r=IntegrationSyncRun.objects.filter(provider='wiw',mode='final_full').order_by('-created_at').first(); assert r is not None, 'No final_full WIW run'; assert r.status == 'success', r.errors; print({'sync_id':str(r.id),'status':r.status,'counts':r.counts,'errors':r.errors})" || return 1

  docker compose exec -T backend python manage.py shell -c "from django.conf import settings; from core.models import User,WorkerProfile,ClientCompany,Location,Position,Shift,TimeEntry,Availability,TimeOffRequest; assert settings.WIW_SYNC_ENABLED is False; print({'users':User.objects.count(),'workers':WorkerProfile.objects.count(),'clients':ClientCompany.objects.count(),'locations':Location.objects.count(),'positions':Position.objects.count(),'shifts':Shift.objects.count(),'times':TimeEntry.objects.count(),'availabilities':Availability.objects.count(),'requests':TimeOffRequest.objects.count(),'wiw_sync_enabled':settings.WIW_SYNC_ENABLED})" | tee "$COUNTS_AFTER" || return 1

  apply_schedule_worker_config || return 1
  docker compose up -d celery celery-beat >/dev/null || return 1
  curl -fsS --retry 12 --retry-delay 5 https://solution.smarbiz.sbs/health/ >/dev/null || return 1
  run_mobile_shift_probe || return 1
  return 0
}

if ! perform_clean_import; then
  echo "WIW bounded clean import or mobile CRUD production probe failed; restoring the exact pre-reset production backup." >&2
  restore_database
  exit 1
fi

chmod 600 "$REPORT_FILE" "$COUNTS_AFTER" || true
cat > "$DONE_MARKER" <<EOF
completed_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
backup=$DB_BACKUP
backup_sha256_file=$DB_CHECKSUM
report=$REPORT_FILE
counts_before=$COUNTS_BEFORE
counts_after=$COUNTS_AFTER
EOF
chmod 600 "$DONE_MARKER"

echo "WIW bounded full reset/import completed and verified."
cat "$DONE_MARKER"
