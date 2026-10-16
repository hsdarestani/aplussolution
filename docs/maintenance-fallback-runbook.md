# A+ Solution — graceful downtime and OpenShift release runbook

**Status: ACTIVE on Cloudflare for browser document navigations (2026-10-16).**

The A+ Solution web and OpenShift changes were released with PR #225.
Production Cloudflare Worker `aplus-availability-fallback` was deployed on
`app.aplus-solution.de/*` after explicit approval (Workflow run
[38923486971](https://github.com/hsdarestani/aplussolution/actions/runs/38923486971)).
The edge route was activated only after confirming proxied DNS and absence of
conflicting routes. The separate Workers.dev staging Worker had passed origin-up,
synthetic HTTP 503 and API/write-isolation tests.

After route activation, public HTML, JSON API, `/maintenance.html`, 404 media
and calendar pass-through were checked. An independent check confirmed
`/__aplus/availability` returns JSON `status:ok` through Cloudflare.
No STRATO service, database, DNS record or mobile binary was changed by edge activation.

**Immediate rollback:** Cloudflare Dashboard → Workers & Pages →
`aplus-availability-fallback` → Domains & Routes → remove the
`app.aplus-solution.de/*` Worker Route ONLY. Leave DNS, STRATO services,
Worker script and database unchanged. Re-validate homepage, API readiness and
calendar/media handling. Route ID recorded in GitHub Actions run summary.

**Scope limit:** Cloudflare fallback covers new browser HTML navigations when
STRATO origin returns a 5xx or connection fails. It cannot make API operations
work during an outage. Native installed app UI changes need a future store build.
Unplanned outage ETA is unknown; the screen does not fabricate estimates.

---

## Why two layers are needed

1. `frontend/src/AppAvailabilityGuard.tsx` displays an A+ branded screen inside a **running**
   web app or newly built Capacitor shell when the DB-aware, read-only \`/api/status/ready/\` endpoint fails
   twice, 6 seconds apart. It preserves authentication, state, forms and history.
   It never forcibly reloads the WebView or resurrects the legacy PWA service worker.
   While healthy, a low-cost heartbeat runs around once per minute; during an
   outage it checks roughly every 30 seconds. When health returns twice, the
   overlay closes and already implemented resume-aware screens refresh.
2. `frontend/public/maintenance.html` is a self-contained fallback with inline
   CSS and JS. It does not load React, CSS bundles, fonts or images from STRATO.
3. `edge/worker.mjs` is an **optional Cloudflare Worker** that must be attached
   separately to the application host. It passes through healthy navigations
   unchanged. If the STRATO frontend/backend fails or the HTML navigation
   times out, it returns the self-contained maintenance page directly from the
   Cloudflare edge with HTTP 503 and Cache-Control: no-store. API, authentication,
   media, downloads and calendar traffic are never replaced by HTML.
   A separate `/__aplus/availability` check verifies **both** the backend + database readiness
   and frontend HTML before the maintenance page redirects back to the app.

The HTML fallback **cannot** help a new visitor during total STRATO outage
until the independent Cloudflare Worker has been deployed and routed.
Old Apple/Android binaries embed frontend assets: changes to the in-app React
guard cannot appear in those already installed binaries without a future mobile
build, though web and browser/PWA builds receive it from the web deployment.
Never tell customers that the native screen is active before confirming a store build.

## Honest return-time policy

- During a planned outage, an operator can set `MAINTENANCE_UNTIL` on the
  edge Worker, e.g. a timezone-aware ISO 8601 timestamp. JavaScript computes
  the remaining minutes as `ceil((until - now) / 60000)` and displays the
  expected Berlin-local completion time. It is a *target*, not a guarantee.
- During unplanned failures, no accurate ETA exists just because an outage
  has started. Do **not** fabricate a “30 minutes” estimate. Instead show
  “Wir prüfen die Verbindung” and the automatic verification cadence.
- `MAINTENANCE_MODE=on` forces the page for a **planned** outage. The availability
  endpoint continues returning unavailable until this flag is removed; this
  avoids an infinite recover → fallback loop.
- `MAINTENANCE_MODE=auto` passes through healthy responses and renders
  fallback only when the HTML navigation fails.
- No permanent incident history is collected. Forecasting from historical
  downtime requires trustworthy independent monitoring and enough comparable
  incidents; this version deliberately avoids unsupported predictions.

## Pre-release validation — no production writes

- Verify the draft PR's backend tests for two independent OpenShift slots,
  no double claims, Service/Housekeeping isolation, and stale slot safety.
- Verify React unit tests: two failed health probes are required before
  overlay; a single transient failure never takes over the app; recovery
  requires consecutive successes.
- Build `frontend` with `npm run build` and verify
  `frontend/public/maintenance.html` ships in `dist`.
- Run a Cloudflare **dry-run** only:
  `cd edge && npx wrangler deploy --dry-run --outdir /tmp/aplus-edge-check`.
  This creates no route, deploy or origin mutation. Inspect resulting bundle.
- Review edge security and access-control. Require that the Worker route
  is attached to the correct Cloudflare account and proxied zone. There
  are no KV bindings, timers, database writes, or user credential handling.
- Exercise a staging origin or separate test route with synthetic 503 / timeout
  / healthy HTML / healthy JSON. Confirm that /api, /calendar, /media,
  and /assets never receive fallback HTML.
- Confirm published/draft assets never cache the status page, and that
  `/__aplus/availability` returns 503 until **both** app components are healthy.

## Future combined release procedure (NOT EXECUTED)

1. Snapshot PostgreSQL state and confirm a unique writable primary. Confirm
   latest replication state and backups. Run read-only health checks on STRATO.
2. Prepare a reversible Cloudflare Worker route on a staging host and test
   origin-down fallback before attaching the production route. Keep the
   current production route unchanged until approval.
3. Activate the Cloudflare fallback at the edge **before** making any backend
   changes. Check that it passes through healthy requests unchanged.
4. Deploy the OpenShift API slot fix together with the web UI/maintenance
   update in the same planned release, without Docker-wide stop or database
   migrations. Use prebuilt images and a health-gated cutover; do not run
   `docker compose up --build` on the memory-constrained primary.
5. Check \`/health/\` and \`/api/status/ready/\`, primary identity, native existing worker account
   OpenShifts (20.10.2026: two open slots 08:30–13:00), and claim atomicity.
   Verify that personal hours are unchanged and HK is not exposed.
6. If any test fails, rollback application version; leave database and
   attached media volumes intact. If the edge fallback itself malfunctions,
   remove its route before attempting further app changes.
7. Schedule the separate Apple/Google build if the owner wants the **in-app**
   guard present in existing native install base. This is not necessary for
   the Cloudflare page on web navigation.

## Non-goals

- Do not cache user data, JWTs, PDF documents or API responses at the edge.
- Do not present a “maintenance” overlay for a single 401, 403, 404 or
  isolated failing optional endpoint.
- Do not clear local storage, force a service worker update, or reload
  unsaved employee time records.
- Do not change production STRATO, DNS, Cloudflare routes or database while
  this PR remains draft.
