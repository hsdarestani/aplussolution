# Phase 4 – Admin exception center and search architecture

Administration starts from actionable exceptions instead of generic KPI dashboards. The Phase 4 scope includes a severity-ordered exception center, global command-style search across operational entities, and server-backed search/filter/sort controls on core list pages.

The exception center surfaces unfilled staffing demand, missing employee check-ins, pending time corrections, unapproved time entries, contract actions/deadlines, incomplete personnel files, failed integrations, absence requests and shift swaps. Staffing remains employee self-service; this phase does not introduce algorithmic worker selection.

Core list search is server-backed so the interface does not silently search only the first paginated page of data. The admin shell also exposes keyboard-driven global search for cross-module navigation.

The final integration keeps the legacy client dashboard intact while admin and manager roles start on the new exception center. Global search is available from the authenticated admin shell and list filters remain scoped to the current module.
