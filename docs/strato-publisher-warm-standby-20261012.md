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

Streaming replication is NOT a historical backup: accidental deletion or corrupt data can replicate. Schedule encrypted versioned backups with point-in-time retention at a separate provider and periodically test a full restore. The two STRATO VPSs share provider-level risk. No automatic failover has been enabled, and full application failover has not been tested. Publisher will remain running during normal standby operation; its 2 vCPU / 4 GB RAM limits may require a resize at actual failover.

## Automation maintenance

Operational workflows currently reside on GitHub branches:
- `hsdarestani/publisher:ops/aplus-standby-20261012`
- `hsdarestani/aplussolution:ops/standby-refresh-20261012`

Do not run the obsolete Hetzner-targeting `BACKUP_HOST` / `BACKUP_PASSWORD` disaster-recovery workflows without review. They describe the retired backup host and can conflict with the new standby.
