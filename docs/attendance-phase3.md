# Phase 3 – Employee-first attendance

## Product rule
Attendance belongs to the employee workflow. Administration handles exceptions, not every normal timer.

## Employee flow
1. A worker can clock in only when a claimed self-service slot or a legacy assigned shift belongs to them and is inside the allowed time window.
2. Location/geofence validation stays active when the shift location has coordinates.
3. The employee sees one active timer, their current eligible shift, monthly worked time, personal history, absence requests and correction status.
4. A finished native A+ entry is never silently edited by the worker. The employee submits a correction request with a reason and requested start/end values.
5. The original native A+ entry remains unchanged until an administrator or manager decides the request.

## Imported WIW history
Historical time entries imported from When I Work remain visible in the employee history, but are immutable audit records after the Phase 2 cutover.

- imported rows are labeled `WIW-Historie · schreibgeschützt` in the employee UI;
- employees cannot create correction requests for imported WIW rows;
- legacy pending correction objects linked to imported WIW rows are not treated as active employee/admin exception workflow;
- administrators/managers cannot approve, close or approve a correction in a way that mutates an imported WIW time entry;
- the original `wiw_time_id` and imported history remain available for audit and traceability.

## Administration flow
The main attendance screen is an exception inbox containing only:
- pending correction requests for native A+ time entries;
- finished but unapproved native A+ time entries;
- native A+ active timers running longer than 12 hours;
- absence requests.

Approved correction requests update the native A+ time entry and record the deciding user. Rejected requests leave the original time entry untouched. Long-running native A+ timers can be closed by administration only with a documented reason; the resulting entry remains unapproved for review.

## Audit / notifications
Correction requests, correction decisions and administrative timer closure are audited. Relevant administrators and employees receive in-app notifications. Imported WIW history is preserved as read-only audit data and is not part of the mutable attendance exception workflow.
