#!/bin/sh
set -e

python manage.py migrate --noinput
# WIW synchronization is disabled. Do not normalize/rename the business-owned
# customer directory on every deploy: customer edits made in A+ must remain the
# source of truth across restarts and releases.
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
