# A+ Solution warm standby on the new STRATO Publisher VPS
Updated: 2026-10-12

## Live topology

- A+ Solution primary: `app.aplus-solution.de`, separate STRATO server. This remains the ONLY writable application.
- Warm standby / Publisher co-location: `82.165.187.14` at STRATO.
- Publisher production: `/opt/aplus-publisher`, ports 80 and 443. Its own PostgreSQL, Redis, Celery and Caddy are separate.
- A+ standby: `/opt/aplussolution-standby/compose.yaml`, independent Docker project, PG 16 image, persistent volume `aplus_solution_standby_pgdata`; database accessible only on Docker network (no host port).
- Replica: physical PostgreSQL streaming from the primary through a restricted SSH IPv6 tunnel, using `aplus_backup_slot` and `aplus-standby-replication-tunnel.service`.
- Runtime snapshot on secondary: `/opt/aplussolution-standby/recovery` (source tarball and confidential environment) and `/opt/aplussolution-standby/media`.
- Source periodic packaging: `aplus-stage-recovery-config.timer` on the primary, every 10 minutes.
- Secondary file synchronisation: `aplus-standby-file-sync.timer`, every 5 minutes, low-priority rsync without delete. Sensitive files are readable only by root on secondary.
- The standby Compose entrypoint requires `standby.signal` to prevent accidental startup as a writer. Do not bypass this during normal operations.

## Validated checks

- Secondary PostgreSQL `pg_is_in_recovery() = true`.
- Secondary `pg_stat_wal_receiver.status = streaming`.
- PostgreSQL WAL receive and replay positions matched in the initial final verification.
- Secondary A+ stack runs the DB only; it does NOT run A+ Celery, Celery Beat, API or Caddy.
- No published DB port on the secondary.
- Uploaded media was successfully copied; source code package and `.env` both present.
- Publisher health confirmed after standby deployment.
- Public A+ Solution continues to return `x-aplus-origin: strato-primary`.
- Verification run: https://github.com/hsdarestani/publisher/actions/runs/38279842703

## Failover (deliberately NOT automatic)

1. Independently verify original primary has truly failed and cannot accept writes. Fence or isolate the primary to avoid split brain.
2. Check latest received WAL and media sync timestamps and document expected data loss, if any.
3. Explicitly authorize standby promotion. Remove the read-only startup guard as part of an independently reviewed failover Compose configuration, and promote PostgreSQL only once.
4. Recreate the A+ application on the new VPS using the recovery source and environment, bind to the *promoted* standby database and recovered media volume; enable ONE set of Celery and notification workers.
5. Resolve the existing port 80/443 conflict: Publisher Caddy already holds both host ports. Update the active reverse proxy for the A+ hostname or use another isolated ingress; do not start the original A+ Caddy Compose unchanged.
6. Verify API, admin portal, worker authentication, real data and outbound push/email with controlled smoke tests BEFORE DNS cutover.
7. Switch Cloudflare origin for `app.aplus-solution.de` only after approval, then confirm production health and origin identity.
8. To recover the old primary later, reseed it as a standby from the new primary; do NOT reintroduce two writable databases.

## Outstanding protections

The first 14-day local versioned history and isolated restoration drill have now been installed and verified (see implementation sections below). **Independent-provider encrypted offsite** protection and full production cutover/fencing automation remain outstanding. The two STRATO VPSs share provider-level risk. Full application failover has not been executed while the primary is healthy; server capacity may need an upgrade during disaster.

## Automation maintenance

Operational workflows currently reside on GitHub branches:
- `hsdarestani/publisher:ops/aplus-standby-20261012`
- `hsdarestani/aplussolution:ops/standby-refresh-20261012`

Do not run the obsolete Hetzner-targeting `BACKUP_HOST` / `BACKUP_PASSWORD` disaster-recovery workflows without review. They describe the retired backup host and can conflict with the new standby.

## Implemented on October 12, 2026: daily history and disaster recovery drill

Historical backups are **installed and running** on the standby host:

- Service: `aplus-standby-snapshot.service`; timer: `aplus-standby-snapshot.timer`, once daily around 03:20 host time, with ten-minute jitter.
- Saved under `/opt/aplussolution-standby/snapshots/backup-YYYYMMDDTHHMMSSZ/`, root-only permissions.
- Each restore point contains a consistent PostgreSQL custom-format `pg_dump`, media tarball, source archive, confidential environment file, a manifest, and SHA-256 checksums.
- Automatic retention of 14 days (daily restore points); initial snapshot and archive integrity verified.
- First installation run: https://github.com/hsdarestani/publisher/actions/runs/38287253772
- A real **isolated restoration rehearsal** successfully restored 78 application tables into an ephemeral PostgreSQL 16 instance with Docker network disabled and CPU/RAM limits; production data and Publisher stayed untouched.
- Restoring a dated snapshot is **separate** from restoring the physical streaming standby; do not run restore commands against the active standby volume.
- Rehearsal workflow run: https://github.com/hsdarestani/publisher/actions/runs/38287952942

## Staged emergency failover toolkit (installed, not activated)

- `/usr/local/sbin/aplus-standby-prepare`: refreshes archived A+ source and validates Docker Compose. Does not promote DB or start writers.
- `/usr/local/sbin/aplus-standby-restore-test`: restores the latest dated database snapshot inside an isolated disposable PostgreSQL container.
- `/usr/local/sbin/aplus-standby-activate --primary-fenced --promote`: **irreversible emergency-only** promotion and startup. It requires the original primary to have been independently fenced and also rejects activation when direct origin HTTPS is still responding. Creates an activation marker, stops incoming replication, promotes the DB, builds and launches the API/web/edge, then safely attaches the Publisher Caddy ingress without conflicting host ports. It deliberately does not start Celery workers yet.
- Manual Cloudflare A and AAAA record changes are required to route `app.aplus-solution.de` to `82.165.187.14`; the original source IP must not remain.
- `/usr/local/sbin/aplus-standby-start-workers --dns-cutover-verified`: launches one worker plus one scheduler **only if** live public HTTPS returns the failover origin header.
- `aplus-failover-ingress-guard.timer`: guard installed, no-op until an explicit failover marker exists; after failover, repairs Publisher Caddy's emergency routing/network membership across Publisher redeploys.
- `/opt/aplussolution-standby/failover-compose.yaml` and `failover-edge.Caddyfile`: separate internal-network services with explicit resource limits. Only the PostgreSQL read-only container runs while in standby state.
- Toolkit installer and safe restore test: https://github.com/hsdarestani/publisher/actions/runs/38287952942

### Mandatory conditions before invoking promotion

1. Independently fence **all old-primary writers** including its PostgreSQL, API, Celery and scheduler, at the VPS/provider level if necessary. An HTTP outage or failed DNS is **not sufficient proof** of fencing.
2. Establish the original host cannot resume accepting writes without an intentional rebuild. Do not invoke the emergency command just to test it.
3. Inspect last replica WAL replay and latest file sync. Expect up to the asynchronous replication lag plus the periodic media sync interval as possible loss.
4. Invoke promotion command from the backup VPS only after the preceding safety conditions are met.
5. Confirm new internal backend is healthy, update Cloudflare DNS, confirm public health and `X-Aplus-Origin: strato-publisher-failover`.
6. Invoke the gated workers command after successful cutover and verify no other active writers or schedulers exist.
7. Treat the **former** primary as a failed/retired instance until reseeded from the new single writer; never let it reconnect unchanged.

### Remaining external dependencies and limitations

- The production-to-reserve promotion was **not executed** (the original primary is healthy); no full production failover cutover or live HTTPS/Cloudflare DNS switch has been tested.
- Standby restores, image builds and internal routing checks are distinct from a full real-production failover rehearsal.
- A separate-provider encrypted **offsite** archive still requires an external storage destination and credentials; 14-day snapshots currently exist on the reserve STRATO VPS, and both VPSs are within STRATO.
- Current replication is asynchronous, not synchronous zero-loss DR.
- The backup host has 2 vCPU and approximately 4 GB RAM and continues to run Publisher. Under genuine failover, workload pressure may require a STRATO server upgrade.
- Do not automatically switch DNS or run background Celery jobs unless independent fencing is proven.
- Toolkit and backup installer workflows are committed on `publisher:ops/aplus-standby-20261012`, not merged into main; deployed host scripts, systemd units and backed-up data are already live.
