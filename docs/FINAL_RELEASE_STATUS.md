# A+ Solution — Final Software Release Status

Date: 2026-08-20

This document supersedes the stale **Known defects found during this audit** section in `QA_FULL_TEST_REPORT.md`.

## Software status

The native A+ Workforce runtime is the operational source of truth. Imported When I Work data remains available only for migration/history where explicitly retained.

### Resolved QA items

- **QA-01 — Shift swap / ShiftSlot:** resolved. Swap creation accepts native claimed-slot ownership, approval transfers only the requester's owned slot, validates the target worker against scheduling rules, and refreshes multi-person shift state.
- **QA-02 — Operations / Steuerzentrale:** resolved. Live operations, schedule quality, upcoming shifts, coverage, conflict, overtime and labor-cost calculations use native `ShiftSlot` assignments with legacy fallback only for historical compatibility.
- **QA-03 — Order automation wording:** resolved. The UI confirms that OpenShifts are created in **A+ Workforce**, not When I Work.
- **Global Search migration noise:** resolved. Synthetic migration-only workers/contracts are removed before result limits are applied.

### Finalized operational paths

The following paths are also native-slot aware so no normal multi-person workflow depends on `Shift.worker`:

- Copy Week preserves every valid claimed worker and open capacity.
- Bulk Publish notifies every assigned worker.
- Schedule CSV expands capacity into worker/open-slot rows.
- Duplicate fallback URLs point to the same canonical native implementation.

## Remaining items are external prerequisites, not software defects

These cannot be manufactured safely from repository code and must use the real production assets/accounts:

- final approved legal DOCX sources for the eight required contract templates;
- Google and Apple OAuth credentials, if not already present in production secrets;
- Android and iOS signing identities;
- Apple App Store / Google Play API credentials and store-side approvals;
- final real-device QA on at least one Android device and one iPhone;
- store review/approval by Apple and Google.

Production readiness endpoints and workflows report these items separately instead of treating missing external credentials or legal documents as application defects.
