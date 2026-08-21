#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py bootstrap
# Contract source files live on the persistent media volume. A database reset can
# remove their FileField pointers while leaving the private files intact. Rebind
# them before Gunicorn starts; missing files stay visible in readiness instead of
# preventing the whole application from booting.
python manage.py recover_document_sources || true

exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120
