# Cloudflare status page — safe activation

The A+ Solution web maintenance page is already published on STRATO. To show it when STRATO itself becomes unreachable, the Worker must live at Cloudflare edge.

## Step 1 — credential and zone audit (NO routing changes)

1. In Cloudflare: **My Profile → API Tokens → Create Token**. Scope it to the account owning `aplus-solution.de`.
2. Include **Workers Scripts Edit / Workers Admin** appropriate to Worker creation, **Workers Routes Write** for the `aplus-solution.de` zone, and **Zone Read** plus **DNS Read** to inspect DNS/proxy settings.
3. GitHub `hsdarestani/aplussolution` → **Settings → Secrets and variables → Actions → New repository secret**. Name the secret `CLOUDFLARE_API_TOKEN`. Paste the token into GitHub only; never paste it into a chat or commit it.
4. Rerun/read `.github/workflows/aplus-cloudflare-readonly-audit.yml`: confirm the zone is active, `app` has proxied DNS (orange cloud), and that no conflicting Worker route already exists.

## Step 2 — isolated Worker preview (NO production route)

Deploy `edge/wrangler.staging.toml` only: `cd edge && npx wrangler deploy --config wrangler.staging.toml`. This deploys **`aplus-availability-fallback-staging` to a distinct `workers.dev` hostname** and does not create any route or DNS changes on `app.aplus-solution.de`.

Staging intentionally permits anonymous GET only, with these paths:

- `/`: read-only anonymous origin homepage request; tests healthy upstream fetching.
- `/__aplus/availability`: confirms both frontend HTML and the DB-aware `/api/status/ready/` response.
- `/__aplus/simulate-outage`: forcibly returns the full German branded HTML maintenance page with HTTP 503, to test origin-down experience without shutting down a service.
- Other paths, including `/api/*`, `/calendar/*`, `/media/*` and `/admin/*`, return 404. Non-GET requests return 405.

Test on a desktop and on a phone. Ensure loading the simulated outage page shows branded design; test retry/recovery; the live production app should remain available throughout.

## Step 3 — main production route (separate approval)

When staging tests pass, use the existing `edge/wrangler.toml` Worker on the zone with an explicitly reviewed Route `app.aplus-solution.de/*`. **Do not configure this Route before checking current proxied DNS and existing Cloudflare Worker rules/routes.** Prefer a manual or dedicated approval-gated workflow. The Worker must let healthy HTML and every API/media/calendar/auth request pass through without modifying them, and only return static 503 HTML if origin HTML navigation is unavailable.

If the Worker introduces any unexpected behavior, immediately remove/disable only this route in the Cloudflare dashboard; leave STRATO, data and DNS records unchanged.

### Scope

This protects web browser navigation when STRATO goes offline, not API writes when PostgreSQL is down and not necessarily the UI inside old installed native mobile app binaries. The status page does not invent an outage ETA. No Cloudflare edge route is active until step 3.
