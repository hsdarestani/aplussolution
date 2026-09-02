# Mobile Dienstplan release — 2026-09-02

This release packages the requested mobile scheduling improvements before production deployment.

## Mobile Dienstplan
- bounded/cache-first mobile schedule feed for faster first paint
- WIW-like composited week swipe
- centered weekday/date headings
- multi-select Service / Housekeeping / Front Office filters
- denser 15-minute time wheel with native haptic ticks
- true multi-select schedule-group controls
- direct native date picker
- compact pause display beside shift time
- Kunde before Jobstandort
- keyboard-safe Note editing and stable extra-options layout
- copy feedback animation
- high-contrast white cards with a compact client accent marker
- approved alphabetic worker picker scope

## Notifications
- foreground in-app push banner plus native local notification presentation when supported
- editable admin/manager push rules by notification family
- configurable enabled state, title template, and body template

## Workforce scope
- applies the approved Dienstplan schedule groups to the named workers only
- all configured workers see all customers for eligible OpenShifts
- removes Lara Mohieddine from workforce
- removes only Julia Stahl's worker profile if her account is a client account
- reapplies the approved scope after WIW syncs/deploy migration flow

## Reporting and sync protection
- filtered Dienstplan PDF by date range, workers, customers and schedule groups
- protects locally edited WIW location names from later sync overwrite
- existing client-company import logic only replaces placeholder customer names

## Release validation
CI must pass backend syntax/configuration, migration drift, backend test coverage, frontend tests, TypeScript/Vite build and Playwright smoke tests before merge. Production deploy reruns migrations, health checks, WIW one-way validation and the production workforce configuration path.
