# A+ Publisher build configuration — A+ Solution

Use this configuration for the `A+ Solution` application in `publisher.smarbiz.sbs`.

## Application

- Framework: `other`
- Repository: `https://github.com/hsdarestani/aplussolution`
- Default branch: `main`
- Android package: `de.aplussolution.workforce`
- iOS bundle ID: `de.aplussolution.workforce`

## build_config

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

Do not put signing passwords, keystores, `.p8` keys, certificates or reviewer credentials in this JSON or in GitHub.
Publisher supplies signing credentials to its ephemeral Linux/macOS build agents only for the active job.

## Android first-upload rule

For a brand-new Google Play app, build and upload the **first AAB with Publisher**. Publisher creates and retains the app's Android upload key and uses the same key for future releases. Download the encrypted/private backup from Publisher immediately after the key is generated and store it securely outside GitHub.

Do not upload a first Play build from the legacy `mobile-store-release.yml` with a different upload key. Google Play associates future uploads with the upload-key certificate. If this package has already been uploaded to Play before, stop before the first Publisher upload and make Publisher use the already-registered upload key instead of generating a different one.

## iOS automatic signing requirements

The Apple Store Account configured in Publisher must include:

- App Store Connect Issuer ID
- Key ID
- `.p8` private key
- Apple Developer Team ID

The API key must have sufficient App Store Connect / Developer Resources permissions for Xcode automatic provisioning and release operations. The App ID `de.aplussolution.workforce` must already exist in the Apple Developer account before the first Publisher build.

The iOS custom build receives only job-scoped environment variables and a temporary `.p8` file; the Publisher cloud Mac removes that temporary key after the build.

## Expected artifacts

- Android: `frontend/android/app/build/outputs/bundle/release/*.aab`
- iOS: `frontend/ios/build/export/*.ipa`

Both build scripts regenerate the Capacitor native project from source, sync the web bundle, apply the approved foreground-only location declarations, and then produce the store artifact.
