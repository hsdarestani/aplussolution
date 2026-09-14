#!/bin/sh
set -e

# A clean staging database intentionally has none of the production workers,
# customer/location records, September 2026 shifts or notification history that
# migrations 0028/0029 repair in production. Mark only those two data-only
# migrations as applied on the first staging bootstrap, while all schema and all
# later migrations still run normally.
if ! python manage.py showmigrations core | grep -q '^ \[X\] 0029_send_spenerhaus_housekeeping_notifications$'; then
  python manage.py migrate core 0027 --noinput
  python manage.py migrate core 0028 --fake --noinput
  python manage.py migrate core 0029 --fake --noinput
fi
python manage.py migrate --noinput

# Keep the normal backend bootstrap sequence aligned with production while all
# external integrations remain disabled by the staging environment.
python manage.py normalize_wiw_directory
python manage.py collectstatic --noinput
python manage.py bootstrap
python manage.py calibrate_signature_templates
python manage.py recover_document_sources || true

exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120
