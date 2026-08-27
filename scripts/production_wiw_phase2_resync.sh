#!/usr/bin/env bash
set -Eeuo pipefail

cd /opt/aplussolution

DONE_MARKER="/root/.aplussolution-wiw-history-scope-v3-20260827.done"
BACKUP_DIR="/root/aplussolution-backups"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DB_BACKUP="$BACKUP_DIR/pre-wiw-phase2-$STAMP.sql.gz"
DB_CHECKSUM="$DB_BACKUP.sha256"
REPORT_FILE="$BACKUP_DIR/wiw-phase2-report-$STAMP.log"
COUNTS_BEFORE="$BACKUP_DIR/pre-wiw-phase2-counts-$STAMP.log"
COUNTS_AFTER="$BACKUP_DIR/post-wiw-phase2-counts-$STAMP.log"
APP_SERVICES_PAUSED=0

if [[ -f "$DONE_MARKER" ]]; then
  echo "WIW Phase 2 history reconciliation already completed; marker: $DONE_MARKER"
  cat "$DONE_MARKER"
  exit 0
fi

resume_app_services() {
  if [[ "$APP_SERVICES_PAUSED" -eq 1 ]]; then
    echo "Restarting backend and background workers after WIW Phase 2 run."
    docker compose up -d backend celery celery-beat >/dev/null 2>&1 || true
    APP_SERVICES_PAUSED=0
  fi
}
trap resume_app_services EXIT

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

DB_USER="$(docker compose exec -T db printenv POSTGRES_USER | tr -d '\r')"
DB_NAME="$(docker compose exec -T db printenv POSTGRES_DB | tr -d '\r')"
: "${DB_USER:?POSTGRES_USER missing}"
: "${DB_NAME:?POSTGRES_DB missing}"

# Capture the exact production state before the maintenance window starts.
docker compose exec -T backend python manage.py shell -c "from core.models import ClientCompany,Location,Position,Shift,TimeEntry; print({'clients':ClientCompany.objects.count(),'active_clients':ClientCompany.objects.filter(active=True).count(),'locations':Location.objects.count(),'active_locations':Location.objects.filter(active=True).count(),'positions':Position.objects.count(),'active_positions':Position.objects.filter(active=True).count(),'shifts':Shift.objects.count(),'wiw_shifts':Shift.objects.exclude(wiw_shift_id__isnull=True).exclude(wiw_shift_id='').count(),'times':TimeEntry.objects.count(),'wiw_times':TimeEntry.objects.exclude(wiw_time_id__isnull=True).exclude(wiw_time_id='').count()})" | tee "$COUNTS_BEFORE"

# Full SQL backup is the rollback boundary. The reconciliation command itself is
# transactional, but keeping a verified backup gives us an independent recovery
# path before any production write is attempted.
docker compose exec -T db pg_dump -U "$DB_USER" -d "$DB_NAME" | gzip -9 > "$DB_BACKUP"
test -s "$DB_BACKUP"
sha256sum "$DB_BACKUP" > "$DB_CHECKSUM"
chmod 600 "$DB_BACKUP" "$DB_CHECKSUM" "$COUNTS_BEFORE"
echo "Phase 2 production backup ready: $DB_BACKUP"

# The host killed reconcile_wiw_history with exit 137 even after Celery was
# stopped. The remaining memory pressure came from the live Gunicorn backend
# (three workers) plus the temporary management-command process. Enter a short
# maintenance window: stop backend + workers, leave DB/Redis/frontend/Caddy up,
# and run exactly one short-lived backend container for reconciliation. The EXIT
# trap always restores the application services if anything fails.
docker compose stop backend celery celery-beat >/dev/null 2>&1 || true
APP_SERVICES_PAUSED=1
echo "Backend and background workers paused for memory-safe WIW Phase 2 reconciliation."

docker compose run --rm --no-deps -T backend python manage.py reconcile_wiw_history --compact | tee "$REPORT_FILE"

# Verify the committed production state from another single-process container,
# while Gunicorn and Celery are still stopped so verification cannot reintroduce
# the same memory-pressure failure mode.
docker compose run --rm --no-deps -T backend python manage.py shell -c "from django.conf import settings; from core.models import ClientCompany,Location,Position,Shift,TimeEntry; from core.workforce_scope import CANONICAL_CLIENTS,CANONICAL_POSITIONS; clients=set(ClientCompany.objects.filter(active=True).values_list('name',flat=True)); positions=set(Position.objects.filter(active=True).values_list('name',flat=True)); assert clients==set(CANONICAL_CLIENTS),(clients,set(CANONICAL_CLIENTS)); assert positions==set(CANONICAL_POSITIONS),(positions,set(CANONICAL_POSITIONS)); assert not Location.objects.filter(active=True,client__active=False).exists(); assert settings.WIW_SYNC_ENABLED is False; print({'active_clients':sorted(clients),'active_positions':sorted(positions),'shifts':Shift.objects.count(),'wiw_shifts':Shift.objects.exclude(wiw_shift_id__isnull=True).exclude(wiw_shift_id='').count(),'times':TimeEntry.objects.count(),'wiw_times':TimeEntry.objects.exclude(wiw_time_id__isnull=True).exclude(wiw_time_id='').count(),'wiw_sync_enabled':settings.WIW_SYNC_ENABLED})" | tee "$COUNTS_AFTER"

# Restore the normal application and prove the public health endpoint is back
# before writing the completion marker.
docker compose up -d backend celery celery-beat >/dev/null
APP_SERVICES_PAUSED=0
curl -fsS --retry 18 --retry-delay 5 https://solution.smarbiz.sbs/health/ >/dev/null

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

echo "WIW Phase 2 history reconciliation completed and verified."
cat "$DONE_MARKER"
