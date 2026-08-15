# A+ Workforce native push setup

Module 6 supports native push end to end. Android registration tokens are delivered through Firebase Cloud Messaging HTTP v1; iOS device tokens are delivered directly through APNs HTTP/2 token authentication.

## Backend environment

### Android / FCM
- `FCM_PROJECT_ID`
- either `FCM_SERVICE_ACCOUNT_JSON` or `FCM_SERVICE_ACCOUNT_FILE`

The service account needs Firebase Cloud Messaging send access.

### iOS / APNs
- `APNS_TEAM_ID`
- `APNS_KEY_ID`
- `APNS_BUNDLE_ID`
- `APNS_PRIVATE_KEY` (the `.p8` key contents; escaped newlines are accepted)
- `APNS_USE_SANDBOX=1` only for development-device builds. App Store builds use the production endpoint by default.

### Optional SMS fallback
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_FROM_NUMBER`

SMS is disabled at workplace level by default and capped at 20 successful messages per user/day.

## Publisher / native build

Android Publisher may provide `ANDROID_GOOGLE_SERVICES_JSON` pointing to the Firebase `google-services.json`. The generated project receives it after `cap add android` so it is not lost when native projects are recreated.

iOS Publisher must use a provisioning profile with the Push Notifications capability. `prepare-native.mjs` patches the generated `AppDelegate.swift`, while `patch-ios-project-signing.py` writes the production `aps-environment` entitlement into the generated App target.

The web build remains functional without native credentials; delivery attempts are recorded as skipped instead of failing application requests.
