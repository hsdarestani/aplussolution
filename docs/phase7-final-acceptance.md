# Phase 7 — Final Integration & Acceptance

Phase 7 is the final integration gate for the completed Phase 1–6 changes. It does not replace working product modules or delete historical WIW / Conversation data.

## Accepted product baseline

1. **Workforce scope** — active customer/position master data stays canonical; historical rows remain available where required for audit/history.
2. **WIW history** — imported historical attendance remains visible but read-only and is not part of native correction workflows.
3. **Attendance** — native A+ attendance/corrections remain the active writable workflow.
4. **Admin/exception UX** — operational exceptions and search stay role-safe and point to native A+ workflows.
5. **Dienstplan & Akten** — the shared card information order and direct Mitarbeiter/Kunden Akte navigation remain stable.
6. **Bestätigung** — confirmation-required assignments keep a per-assignee `Ausstehend / Bestätigt / Abgelehnt` decision.
7. **Mitteilungen** — active Chat is replaced by one-way administrative Mitteilungen with selected/all recipients, attachment support, push integration, history and read state.

## Communication invariant

- Admin/Manager may create Mitteilungen.
- Worker/client may only receive/read Mitteilungen addressed to them.
- The active frontend must not call `conversations/` or `portal/message-recipients/` and must not expose a reply/new-conversation composer.
- Legacy Conversation/Message backend storage/API may remain for backward compatibility and historical integrity only.

## Acceptance gates

A Phase 7 release is accepted only when all of the following are green on the same head:

- Django configuration check and migration consistency.
- Full backend test suite with coverage.
- Frontend unit tests and production build.
- Full Chromium Browser E2E/mobile QA.
- Phase 7 cross-phase acceptance tests.
- Main-branch production deployment and final deployment-status job.

External credentials, legal template approvals and app-store approvals remain external prerequisites and are not manufactured by Phase 7.
