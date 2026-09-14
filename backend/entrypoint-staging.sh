#!/bin/sh
set -e

# A clean staging database intentionally does not contain the production workers,
# customer/location records and September 2026 shifts expected by migration 0028.
# Apply the real schema through 0027, record that production-only data migration
# as satisfied, then continue every later migration normally.
python manage.py migrate core 0027 --noinput
python manage.py migrate core 0028 --fake --noinput
python manage.py migrate --noinput

# Keep the normal backend bootstrap sequence aligned with production while all
# external integrations remain disabled by the staging environment.
python manage.py normalize_wiw_directory
python manage.py collectstatic --noinput
python manage.py bootstrap
python manage.py calibrate_signature_templates
python manage.py recover_document_sources || true

exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120
