# Operational native push notifications

A+ Solution creates a database `Notification` for workforce events; the existing notification signal forwards it to registered native devices through FCM (Android) or APNs (iOS).

## Workforce events

- New/published OpenShift: notify eligible active employees.
- AI-created OpenShift: notify eligible active employees.
- Copied/released OpenShift: notify eligible active employees.
- Admin assignment: notify the assigned employee immediately.
- Shift edit/removal: notify the affected assigned employee(s).
- Check-in/check-out: notify active admin/manager accounts immediately.
- Missing check-in/check-out: remind the employee after `ATTENDANCE_REMINDER_MINUTES` (default 15); Celery checks every five minutes.
- Employee/customer registration completion: notify active admin/manager accounts once. The onboarding transition is primary; first successful login is an idempotent fallback for legacy accounts.

## Production credentials

Android backend delivery:
- `FIREBASE_PROJECT_ID`
- `FIREBASE_CREDENTIALS_JSON`

Android app client configuration:
- `frontend/firebase/google-services.json` (checked-in client config) or build-time `GOOGLE_SERVICES_JSON_BASE64`.

iOS backend delivery:
- `APNS_TEAM_ID`
- `APNS_KEY_ID`
- `APNS_PRIVATE_KEY`
- `APNS_BUNDLE_ID=de.aplussolution.workforce`
- `APNS_USE_SANDBOX=0` for App Store production builds.

The iOS provisioning profile must include the Push Notifications entitlement.
