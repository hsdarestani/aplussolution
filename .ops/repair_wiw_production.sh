#!/usr/bin/env bash
set -euo pipefail

cd /opt/aplussolution

grep -q 'USER_CONTEXT_CACHE_KEY' backend/core/wiw.py
docker compose exec -T backend python -c "from core.wiw import WhenIWorkClient; assert hasattr(WhenIWorkClient, 'resolve_user_context'); print('CONTAINER_FIX_PRESENT true')" </dev/null

docker compose exec -T backend python manage.py migrate --noinput </dev/null
docker compose exec -T backend python manage.py check </dev/null

BACKEND_ID=$(docker compose ps -q backend)
test -n "$BACKEND_ID"
docker cp /root/verify_wiw_production.py "$BACKEND_ID":/tmp/verify_wiw_production.py
docker compose exec -T backend sh -c 'python manage.py shell < /tmp/verify_wiw_production.py' </dev/null
docker compose exec -T backend rm -f /tmp/verify_wiw_production.py </dev/null
rm -f /root/verify_wiw_production.py /root/repair_wiw_production.sh

docker compose exec -T backend curl -fsS http://127.0.0.1:8000/health/ >/dev/null </dev/null
curl -fsS https://solution.smarbiz.sbs/health/ >/dev/null
HTTP_CODE=$(curl -sS -o /tmp/login-check.json -w '%{http_code}' -X POST https://solution.smarbiz.sbs/api/auth/login/ -H 'Content-Type: application/json' --data '{"email":"invalid@example.com","password":"invalid"}')
test "$HTTP_CODE" != 502
test "$HTTP_CODE" != 503
echo "PUBLIC_LOGIN_HTTP $HTTP_CODE"
echo "WIW_PRODUCTION_FIX_VERIFIED true"
