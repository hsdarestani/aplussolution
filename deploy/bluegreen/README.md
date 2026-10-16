# A+ Solution — Blue Green release plan (STAGED ONLY)

**No production deployment has been performed.** This plan is staged in draft
PR #225 together with the per-slot OpenShift cards and the maintenance page.

## Why the old deployment is unsafe

The old `.github/workflows/deploy.yml` stops and removes `backend`,
`frontend` and `caddy` before recreating them. It also builds images
on the primary, reruns migrations and bootstrap, and can stall when the host
is out of CPU, RAM or Docker storage. It cannot deliver zero downtime.

The legacy **deploy** job is explicitly disabled in this branch. Its CI
`validate` job remains available. Do not restore the legacy push-to-deploy
condition or manually execute it during the new release.

## Proposed topology

Current blue stack is left **running**:
`aplussolution-backend-1`, `aplussolution-frontend-1`,
`aplussolution-caddy-1`, PostgreSQL, Redis, Celery, Celery Beat,
media and static volumes.

New green stack is intentionally tiny and separate:
`aplusgreen-backend-green-1` and `aplusgreen-frontend-green-1`.
Both join the existing `aplussolution_default` Docker network.
No new PostgreSQL, Redis, Celery, background jobs, public ports or Caddy.
The green backend uses the existing primary DB and media volume and runs
**Gunicorn directly** so the legacy entrypoint's database migration,
bootstrap, catalog updates and collectstatic do not execute on staging.
The existing blue Celery services remain the only background workers.

The green memory limit is ~1.2 GiB total plus overhead. A manual
preflight refuses to stage when available RAM is below 1800 MiB or Docker
disk free space below 6 GiB. **These are conservative minimums, not
a proof of sufficient host capacity.** If STRATO cannot satisfy this
preflight reliably, use a separate staging host with the same primary
database path and appropriately restricted routing instead. Never force
parallel containers onto a memory-constrained host.

The blue Caddy instance stays up. When green is healthy, validate a
transformed temporary Caddyfile that routes frontend and backend to green;
switch by **Caddy config reload**, not container restart. Leave original
Caddyfile and blue containers intact. In an error, restore the original
Caddyfile by Caddy reload. If the whole host fails, the independent
Cloudflare maintenance fallback is still required.

## Prerequisites — before any future approval

1. Resolve all targeted backend tests, frontend build and relevant
   Playwright smoke checks. PR #225 remains draft until the owner explicitly
   authorizes a combined release.
2. Perform a read-only production resource check (RAM, disk, active images,
   persistent volumes, current container IDs, DB readiness). Do not stage
   green if SSH, Docker or the origin show degraded behavior.
3. Validate backups and establish a **single writable PostgreSQL primary**.
   A physical replica must not be promoted or written concurrently.
4. Confirm that the new backend requires **no database schema migration**.
   The green staging process runs `manage.py migrate --check` only.
5. Confirm the Cloudflare Worker is attached to the correct proxied zone on
   a test route first. It must pass API/calendar/media traffic unchanged
   and show the self-contained page only for failed HTML navigations.
6. Authenticate the primary to GHCR using a least-privilege *read-only*
   package token through a secure interactive Docker login. The token is
   never committed and is not read from a GitHub PR.

## Immutable images built away from STRATO

A separate **manual-only** GitHub workflow
`.github/workflows/bluegreen-build-images.yml` requires the exact input
`BUILD_ONLY` and builds backend and frontend on a GitHub runner. It publishes
SHA-tagged images to GHCR and prints their immutable `@sha256:` digests.
It **does not connect to STRATO or alter Cloudflare**.

When ready, securely copy `deploy/bluegreen/compose.green.yml` and
`deploy/bluegreen/release.sh` to a dedicated `/opt/aplussolution-green/`
directory on the primary. Set executable bit on the shell script.
Create a private `images.env` file in that directory containing exactly:

```ini
BACKEND_IMAGE=ghcr.io/OWNER/aplus-bluegreen-backend@sha256:VERIFIED_DIGEST
FRONTEND_IMAGE=ghcr.io/OWNER/aplus-bluegreen-frontend@sha256:VERIFIED_DIGEST
```

`OWNER` and digests must come from the successful build. The file is a
host-only manifest, **not** a repository file.

## Future steps (DO NOT RUN TODAY)

```bash
sudo /opt/aplussolution-green/release.sh preflight
sudo /opt/aplussolution-green/release.sh stage

# Inspect green logs and perform authorized staging smoke tests.
# Only after explicit approval and a working Cloudflare safety net:
sudo /opt/aplussolution-green/release.sh cutover I_APPROVE_CUTOVER

# Fast manual recovery if errors are observed:
sudo /opt/aplussolution-green/release.sh rollback I_APPROVE_ROLLBACK
```

Stage only pulls prebuilt images and starts **green** containers.
Cutover only updates Caddy's **in-memory config**, preserving the original
mounted blue config for fail-safe host restarts. It checks the green
DB-aware readiness and HTML endpoints 12 times. Any failed cutover
attempt triggers a best-effort runtime rollback.

A subsequent **separately approved persistence step** is required after
a soak period to make the green routing survive Caddy container
replacement and host restart. Until then, a host restart reverts to
the original blue version, which is intentionally safer than pinning
an unproven green version. Do not remove blue containers or replace the
mounted production Caddyfile during the initial cutover.

## Release acceptance checks

- `/health/` remains reachable and `/api/status/ready/` returns OK
  against the live DB after switching routes.
- Worker Francesco's 20.10.2026 OpenShifts shows two 08:30–13:00
  Servicekraft cards. The two cards retain distinct slot UUIDs and one
  shared parent Shift UUID.
- Claiming a slot consumes **exactly** that open slot; a stale slot
  request fails instead of consuming another one.
- Service workers do not receive Housekeeping vacancies.
- Personal hour totals remain unchanged until an actual assignment.
- Login, PDF, calendar feeds, file uploads and push configuration work.
- Cloudflare fallback has been tested separately with deliberate 503s,
  origin timeouts and recovery; no fake restoration ETA is shown.

## Limits

A single STRATO host cannot guarantee perfect zero downtime during
hardware failure or kernel/Docker/network outage. The goal is
**near-zero interruption for controlled software releases**.
The independent Cloudflare status page cannot make backend API writes
available while PostgreSQL is down.

Already published native apps use bundled UI code. API-side OpenShift
slot-row compatibility should work without a store release once backend
is deployed, but in-app maintenance overlay UI requires a future native
store build. Cloudflare serves browser navigation independently.

## Safety baseline

- Never run `docker compose stop`, `rm`, `down`, `build` or
  `up --remove-orphans` on the production project for this upgrade.
- Never run migrations automatically in the staging containers.
- Never stage without confirming memory, disk and unique DB primary.
- Never change production DNS or proxy config from the CI-only PR.
- Keep deployment controls manual until reviewed and approved.
