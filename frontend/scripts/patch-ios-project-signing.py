#!/usr/bin/env python3
import os
import re
from pathlib import Path

project = Path("ios/App/App.xcodeproj/project.pbxproj")
if not project.exists():
    raise SystemExit(f"Xcode project not found: {project}")

required = [
    "IOS_TEAM_ID",
    "IOS_BUNDLE_ID",
    "IOS_CODE_SIGN_IDENTITY",
    "IOS_PROVISIONING_PROFILE_SPECIFIER",
    "IOS_SIGNING_KEYCHAIN",
    "APP_VERSION_NAME",
    "APP_BUILD_NUMBER",
]
missing = [name for name in required if not os.environ.get(name)]
if missing:
    raise SystemExit("Missing Publisher iOS signing variables: " + ", ".join(missing))


def pbx_quote(value: str) -> str:
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def set_setting(body: str, key: str, value: str, indent: str) -> str:
    pattern = re.compile(rf"(?m)^(?P<indent>\s*){re.escape(key)}\s*=\s*[^;]*;\s*$")
    replacement = rf"\g<indent>{key} = {value};"
    body, count = pattern.subn(replacement, body)
    if count == 0:
        if body and not body.endswith("\n"):
            body += "\n"
        body += f"{indent}{key} = {value};\n"
    return body


text = project.read_text()
block_pattern = re.compile(
    r"(?P<head>[A-F0-9]+ /\* (?:Debug|Release) \*/ = \{\n\s*isa = XCBuildConfiguration;\n\s*buildSettings = \{\n)"
    r"(?P<body>.*?)"
    r"(?P<tail>\s*\};\n\s*name = (?:Debug|Release);\n\s*\};)",
    re.S,
)

patched = 0


def patch_block(match: re.Match) -> str:
    global patched
    body = match.group("body")
    # Only the application target's build configurations carry the product bundle ID.
    # CocoaPods targets live in Pods.xcodeproj and must never receive an app provisioning profile.
    if "PRODUCT_BUNDLE_IDENTIFIER" not in body:
        return match.group(0)

    bundle_match = re.search(r"(?m)^(\s*)PRODUCT_BUNDLE_IDENTIFIER\s*=", body)
    indent = bundle_match.group(1) if bundle_match else "\t\t\t\t"

    settings = {
        "CODE_SIGN_STYLE": "Manual",
        "CODE_SIGN_IDENTITY": pbx_quote(os.environ["IOS_CODE_SIGN_IDENTITY"]),
        "DEVELOPMENT_TEAM": os.environ["IOS_TEAM_ID"],
        "PROVISIONING_PROFILE_SPECIFIER": pbx_quote(os.environ["IOS_PROVISIONING_PROFILE_SPECIFIER"]),
        "OTHER_CODE_SIGN_FLAGS": pbx_quote("--keychain " + os.environ["IOS_SIGNING_KEYCHAIN"]),
        "PRODUCT_BUNDLE_IDENTIFIER": os.environ["IOS_BUNDLE_ID"],
        "MARKETING_VERSION": os.environ["APP_VERSION_NAME"],
        "CURRENT_PROJECT_VERSION": os.environ["APP_BUILD_NUMBER"],
    }
    for key, value in settings.items():
        body = set_setting(body, key, value, indent)

    patched += 1
    return match.group("head") + body + match.group("tail")


text = block_pattern.sub(patch_block, text)
if patched < 2:
    raise SystemExit(f"Expected to patch App Debug/Release configurations, patched {patched}.")

project.write_text(text)
print(f"Scoped manual App Store signing to the App target in {patched} Xcode configurations.")
