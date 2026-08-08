# A+ Solution — Public Store Release

This file overrides the earlier private/unlisted distribution recommendation for the current release goal.

## Distribution goal

A+ Solution must be publicly visible under the A+ Solution developer profile on both stores.

- Google Play: **Public production listing**
- Apple App Store: **Public Distribution** (discoverable on the App Store)
- No Managed Google Play private restriction
- No Apple Private Custom App distribution
- No Apple Unlisted request

The application itself remains access-controlled:

- No public self-registration
- Company-provisioned employee/manager accounts only
- Store reviewers receive a dedicated reusable synthetic review account
- Public users may download the app but cannot access company data without an authorized account

## Store review positioning

Describe the app accurately as the official workforce application of A+ Solution GmbH. Do not imply that downloading the app creates an account or grants employment access.

Recommended review note:

```text
A+ Solution is the official workforce application of A+ Solution GmbH. The application is publicly distributed on the App Store / Google Play, while operational access is restricted to employees and management whose accounts are provisioned by A+ Solution GmbH. There is no public self-registration.

Reviewer access:
Email: [REVIEW_EMAIL]
Password: [REVIEW_PASSWORD]

The reviewer account is reusable, does not require OTP/2FA, works regardless of reviewer location, and contains synthetic data only.

Precise location is requested only when a user deliberately clocks in or out for a geofenced worksite. No background location or advertising tracking is used.
```

## Android public release requirement

The Publisher native-preparation step enforces Android 16 / API 36 for both `compileSdkVersion` and `targetSdkVersion`, so the first public build is ready for Google Play's requirement taking effect on 31 August 2026.

## Publisher build configuration

Use the existing configuration in `docs/PUBLISHER_BUILD_CONFIG.md`:

```json
{
  "android_command": "bash frontend/scripts/build-publisher-android.sh",
  "android_artifact": "frontend/android/app/build/outputs/bundle/release/*.aab",
  "ios_command": "bash frontend/scripts/build-publisher-ios.sh",
  "ios_artifact": "frontend/ios/build/export/*.ipa",
  "env": {
    "VITE_API_URL": "https://solution.smarbiz.sbs/api"
  }
}
```

## First Android upload

The first AAB for package `de.aplussolution.workforce` must be built by A+ Publisher using its persistent upload key. Do not establish the Play app with an AAB signed by a different upload key.

## Apple distribution setting

In App Store Connect choose:

`Pricing and Availability → App Distribution Methods → Public`

Do not choose Private and do not request Unlisted distribution for this release.
