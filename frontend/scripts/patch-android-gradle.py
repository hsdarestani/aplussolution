#!/usr/bin/env python3
import os
import re
from pathlib import Path

path = Path("android/app/build.gradle")
root_path = Path("android/build.gradle")
text = path.read_text()
version_name = os.environ["APP_VERSION_NAME"]
build_number = int(os.environ["APP_BUILD_NUMBER"])

signing_block = '''    signingConfigs {
        release {
            storeFile file("aplus-release.jks")
            storePassword System.getenv("ANDROID_KEYSTORE_PASSWORD")
            keyAlias System.getenv("ANDROID_KEY_ALIAS")
            keyPassword System.getenv("ANDROID_KEY_PASSWORD")
        }
    }
'''

if "signingConfigs {" not in text:
    if "android {" not in text:
        raise SystemExit("Could not find the Android configuration block.")
    text = text.replace("android {", "android {\n" + signing_block, 1)

# Only target the release build type, never signingConfigs.release.
if "signingConfig signingConfigs.release" not in text:
    pattern = re.compile(r"(buildTypes\s*\{\s*release\s*\{)")
    text, count = pattern.subn(
        r"\1\n            signingConfig signingConfigs.release",
        text,
        count=1,
    )
    if count != 1:
        raise SystemExit("Could not find buildTypes.release in Android build.gradle.")

text, version_code_count = re.subn(
    r"\bversionCode\s+\d+",
    f"versionCode {build_number}",
    text,
    count=1,
)
text, version_name_count = re.subn(
    r'\bversionName\s+["\'][^"\']+["\']',
    f'versionName "{version_name}"',
    text,
    count=1,
)
if version_code_count != 1 or version_name_count != 1:
    raise SystemExit("Could not set Android versionCode/versionName from Publisher release metadata.")

# Guard against the exact regression that caused the first Publisher build to fail.
signing_section = re.search(r"signingConfigs\s*\{(?P<body>.*?)\n\s*\}\s*\n\s*(?:buildTypes|defaultConfig|compileSdk)", text, re.S)
if signing_section and "signingConfig signingConfigs.release" in signing_section.group("body"):
    raise SystemExit("Invalid Gradle patch: signingConfig was inserted inside signingConfigs.")

if not re.search(r"buildTypes\s*\{\s*release\s*\{[^}]*signingConfig\s+signingConfigs\.release", text, re.S):
    raise SystemExit("Invalid Gradle patch: release build type is not linked to release signing config.")

# Firebase Messaging requires the Google Services Gradle plugin so the checked-in
# google-services.json is converted into Android resources at build time.
google_services = Path("android/app/google-services.json")
if google_services.exists():
    root = root_path.read_text()
    plugin_line = "classpath 'com.google.gms:google-services:4.4.2'"
    if plugin_line not in root:
        root, count = re.subn(
            r"(dependencies\s*\{)",
            r"\1\n        " + plugin_line,
            root,
            count=1,
        )
        if count != 1:
            raise SystemExit("Could not add Google Services classpath to android/build.gradle.")
        root_path.write_text(root)
    apply_line = "apply plugin: 'com.google.gms.google-services'"
    if apply_line not in text:
        text = text.rstrip() + "\n\n" + apply_line + "\n"

path.write_text(text)
