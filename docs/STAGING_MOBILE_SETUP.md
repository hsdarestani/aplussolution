# A+ Solution Mobile Staging

This branch is the canonical source for the separate Google Play / Apple TestFlight staging apps.
Production remains on `main`.

## Identity

| Environment | App name | Android package / iOS bundle |
| --- | --- | --- |
| Production | A+ Solution | `de.aplussolution.workforce` |
| Staging | A+ Solution Staging | `de.aplussolution.staging` |

## Staging backend

The mobile staging build uses:

`https://staging.app.aplus-solution.de/api`

The staging build scripts refuse the known production APIs. Do not override this with a production endpoint.

## Publisher commands

Use a separate Publisher application/release target for staging.

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
VITE_API_URL=https://staging.app.aplus-solution.de/api
```

For iOS, Publisher must set `IOS_BUNDLE_ID=de.aplussolution.staging` together with the normal Apple Team/signing values for the staging App ID.

## Android Firebase / push

The staging build never falls back to the checked-in production `frontend/firebase/google-services.json`.

When native push is needed in staging, create/register Android package `de.aplussolution.staging` in the staging Firebase project and provide one of these to Publisher:

- `GOOGLE_SERVICES_JSON_BASE64`
- `GOOGLE_SERVICES_JSON`

Then set `REQUIRE_NATIVE_PUSH=1`.
The build validates that the supplied Firebase JSON actually contains package `de.aplussolution.staging`.

Until staging Firebase is configured, the staging Android app can build without native push.

## iOS push

The generated Xcode project uses the staging bundle ID and attaches the APNs entitlement to that exact ID. The staging provisioning profile must include Push Notifications if staging push is enabled.

## Release flow

1. Changes are integrated into `staging` first.
2. Publisher builds the separate staging Android/iOS apps.
3. Test through Google Play Internal Testing and Apple TestFlight.
4. After approval, promote the verified code to `main`.
5. Production is built only from `main` with the production Publisher targets.

## Safety rules

- Never use `de.aplussolution.workforce` for a staging build.
- Never point staging at a production API.
- Never reuse the production Android Firebase JSON in staging.
- Never put signing keys, `.p8` files, keystores, passwords or reviewer credentials in GitHub.
