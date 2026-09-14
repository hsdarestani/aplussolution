# A+ Solution Mobile Staging

This branch is the canonical source for the separate Google Play / Apple TestFlight staging apps.
Production remains on `main`.

## Identity

| Environment | App name | Android package / iOS bundle |
| --- | --- | --- |
| Production | A+ Solution | `de.aplussolution.workforce` |
| Staging | A+ Solution Staging | `de.aplussolution.staging` |

The native client sends its active app ID with every push-device registration. The backend rejects device tokens from another environment and only delivers to devices whose `app_id` matches its own `NATIVE_APP_ID`.

## Staging backend

The mobile staging build uses:

`https://staging.app.aplus-solution.de/api`

The staging stack has its own PostgreSQL database, Redis, media/static volumes and device-token table. It does not read production application data.

For push transport only, the staging deploy copies the existing FCM service-account and APNs auth-key credentials read-only from the production `.env` on the same Strato host. Those provider credentials are account/team credentials and are reused without sharing users, devices, notifications or business data.

Staging overrides:

```text
NATIVE_APP_ID=de.aplussolution.staging
APNS_BUNDLE_ID=de.aplussolution.staging
APNS_USE_SANDBOX=0
```

`APNS_USE_SANDBOX=0` is intentional: TestFlight/App Store distribution builds receive production-environment APNs device tokens even though the app itself is a staging app.

The staging deploy fails its push-readiness assertion unless both backend providers are configured.

## Publisher commands

Use the separate Publisher application/release target for staging.

Android command:

```bash
bash frontend/scripts/build-publisher-android-staging.sh
```

Android artifact:

```text
frontend/android/app/build/outputs/bundle/release/*.aab
```

iOS command:

```bash
bash frontend/scripts/build-publisher-ios-staging.sh
```

iOS artifact:

```text
frontend/ios/build/export/*.ipa
```

Publisher environment:

```text
APP_ENV=staging
CAPACITOR_APP_ID=de.aplussolution.staging
CAPACITOR_APP_NAME=A+ Solution Staging
VITE_APP_ENV=staging
VITE_NATIVE_APP_ID=de.aplussolution.staging
VITE_API_URL=https://staging.app.aplus-solution.de/api
REQUIRE_NATIVE_PUSH=1
IOS_BUNDLE_ID=de.aplussolution.staging
```

Both staging build wrappers now default to `REQUIRE_NATIVE_PUSH=1`, so a store build cannot silently ship without native push support.

## Android Firebase / FCM

The staging build never falls back to the checked-in production `frontend/firebase/google-services.json`.

Use the existing Firebase project if desired, but register a separate Android Firebase app with package:

```text
de.aplussolution.staging
```

Download the resulting staging `google-services.json` and provide it to Publisher as either:

```text
GOOGLE_SERVICES_JSON_BASE64=<base64 of staging google-services.json>
```

or:

```text
GOOGLE_SERVICES_JSON=<raw staging google-services.json>
```

The build fails if the supplied file does not contain `de.aplussolution.staging`.

The backend FCM service account may remain the same as production when both Firebase Android apps are registered in the same Firebase project; device tokens remain app/package scoped and the A+ backend additionally isolates them by `NATIVE_APP_ID`.

## iOS APNs

In Apple Developer, the App ID for:

```text
de.aplussolution.staging
```

must have the **Push Notifications** capability enabled.

After enabling it, regenerate/download the App Store distribution provisioning profile used by Publisher for the staging bundle ID. The profile must contain the APS entitlement.

The build script adds:

```text
aps-environment = production
```

for the push-enabled staging archive. This is correct for TestFlight/App Store distribution.

The backend may reuse the existing dedicated APNs Auth Key (`.p8`, Key ID, Team ID); it sends with APNs topic `de.aplussolution.staging`. Do not use a Sign in with Apple key or an App Store Connect API key as the APNs key.

## Push verification

After installing the new push-enabled staging build and logging in:

1. Allow notification permission when prompted.
2. Call/view `GET /api/push/status/` while authenticated.
3. Confirm `app_id` is `de.aplussolution.staging`.
4. Confirm the current platform has at least one active device.
5. Trigger a normal in-app notification event (shift assignment/change, message, etc.).
6. Verify foreground presentation, background notification and notification-tap navigation.
7. Verify the same event does not appear in the production app unless independently generated in production.

## Release flow

1. Changes are integrated into `staging` first.
2. Staging deploy and validation must be green.
3. Publisher builds the separate push-enabled staging Android/iOS apps.
4. Test through Google Play Internal Testing and Apple TestFlight.
5. After approval, promote the verified code to `main`.
6. Production is built only from `main` with the production Publisher targets.

## Safety rules

- Never use `de.aplussolution.workforce` for a staging build.
- Never point staging at a production API.
- Never reuse the production Android `google-services.json` for staging.
- Reusing the same Firebase project service account is allowed only when a distinct Firebase Android app exists for `de.aplussolution.staging`.
- Reusing the same APNs Auth Key is allowed, but the staging App ID/profile must have Push Notifications enabled and the APNs topic must remain `de.aplussolution.staging`.
- Never put `.p8` files, keystores, service-account private keys, passwords or reviewer credentials in GitHub.
