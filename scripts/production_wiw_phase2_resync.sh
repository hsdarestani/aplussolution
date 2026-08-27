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

# IMPORTANT: stop Gunicorn/Celery before starting *any* extra Django process.
# The previous maintenance-mode attempt still ran the pre-count through the live
# three-worker backend and was OOM-killed before it reached the stop command.
docker compose stop backend celery celery-beat >/dev/null 2>&1 || true
APP_SERVICES_PAUSED=1
echo "Backend and background workers paused before Phase 2 Django processes."

# Capture the exact pre-write state from a single short-lived Django container.
docker compose run --rm --no-deps -T backend python manage.py shell -c "from core.models import ClientCompany,Location,Position,Shift,TimeEntry; print({'clients':ClientCompany.objects.count(),'active_clients':ClientCompany.objects.filter(active=True).count(),'locations':Location.objects.count(),'active_locations':Location.objects.filter(active=True).count(),'positions':Position.objects.count(),'active_positions':Position.objects.filter(active=True).count(),'shifts':Shift.objects.count(),'wiw_shifts':Shift.objects.exclude(wiw_shift_id__isnull=True).exclude(wiw_shift_id='').count(),'times':TimeEntry.objects.count(),'wiw_times':TimeEntry.objects.exclude(wiw_time_id__isnull=True).exclude(wiw_time_id='').count()})" | tee "$COUNTS_BEFORE"

# Full SQL backup is the independent rollback boundary. Nothing has written to
# the database yet; the application remains paused while pg_dump runs.
docker compose exec -T db pg_dump -U "$DB_USER" -d "$DB_NAME" | gzip -9 > "$DB_BACKUP"
test -s "$DB_BACKUP"
sha256sum "$DB_BACKUP" > "$DB_CHECKSUM"
chmod 600 "$DB_BACKUP" "$DB_CHECKSUM" "$COUNTS_BEFORE"
echo "Phase 2 production backup ready: $DB_BACKUP"

# Run the transactional import/reconciliation as the only Django process on the host.
docker compose run --rm --no-deps -T backend python manage.py reconcile_wiw_history --compact | tee "$REPORT_FILE"

# Verify the committed production state in a fresh single-process container while
# Gunicorn/Celery remain stopped, avoiding the same memory-pressure failure mode.
docker compose run --rm --no-deps -T backend python manage.py shell -c "from django.conf import settings; from core.models import ClientCompany,Location,Position,Shift,TimeEntry; from core.workforce_scope import CANONICAL_CLIENTS,CANONICAL_POSITIONS; clients=set(ClientCompany.objects.filter(active=True).values_list('name',flat=True)); positions=set(Position.objects.filter(active=True).values_list('name',flat=True)); assert clients==set(CANONICAL_CLIENTS),(clients,set(CANONICAL_CLIENTS)); assert positions==set(CANONICAL_POSITIONS),(positions,set(CANONICAL_POSITIONS)); assert not Location.objects.filter(active=True,client__active=False).exists(); assert settings.WIW_SYNC_ENABLED is False; print({'active_clients':sorted(clients),'active_positions':sorted(positions),'shifts':Shift.objects.count(),'wiw_shifts':Shift.objects.exclude(wiw_shift_id__isnull=True).exclude(wiw_shift_id='').count(),'times':TimeEntry.objects.count(),'wiw_times':TimeEntry.objects.exclude(wiw_time_id__isnull=True).exclude(wiw_time_id='').count(),'wiw_sync_enabled':settings.WIW_SYNC_ENABLED})" | tee "$COUNTS_AFTER"

# Restore the normal application and prove public health before the completion marker.
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
