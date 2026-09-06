#!/bin/sh
set -e

python manage.py migrate --noinput
# Keep the business-owned A+ customer/location directory canonical before any
# worker/web process starts consuming WIW data. The command is idempotent and
# preserves all historical WIW ids as aliases on the canonical locations.
python manage.py normalize_wiw_directory
python manage.py collectstatic --noinput
python manage.py bootstrap
# Bootstrap refreshes the standard document catalog, so apply measured signature
# coordinates afterwards. This keeps calibrated legal-document fields stable on
# every deployment instead of falling back to heuristic PDF placement.
python manage.py calibrate_signature_templates
# Contract source files live on the persistent media volume. A database reset can
# remove their FileField pointers while leaving the private files intact. Rebind
# them before Gunicorn starts; missing files stay visible in readiness instead of
# preventing the whole application from booting.
python manage.py recover_document_sources || true

exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120
