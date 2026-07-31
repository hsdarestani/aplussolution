# Phase 3 – Employee-first attendance

## Product rule
Attendance belongs to the employee workflow. Administration handles exceptions, not every normal timer.

## Employee flow
1. A worker can clock in only when a claimed self-service slot or a legacy assigned shift belongs to them and is inside the allowed time window.
2. Location/geofence validation stays active when the shift location has coordinates.
3. The employee sees one active timer, their current eligible shift, monthly worked time, personal history, absence requests and correction status.
4. A finished entry is never silently edited by the worker. The employee submits a correction request with a reason and requested start/end values.
5. The original entry remains unchanged until an administrator or manager decides the request.

## Administration flow
The main attendance screen is an exception inbox containing only:
- pending correction requests;
- finished but unapproved time entries;
- active timers running longer than 12 hours;
- absence requests.

Approved correction requests update the time entry and record the deciding user. Rejected requests leave the original time entry untouched. Long-running timers can be closed by administration only with a documented reason; the resulting entry remains unapproved for review.

## Audit / notifications
Correction requests, correction decisions and administrative timer closure are audited. Relevant administrators and employees receive in-app notifications.
