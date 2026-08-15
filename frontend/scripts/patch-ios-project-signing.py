#!/usr/bin/env python3
import os
import re
from pathlib import Path

project = Path("ios/App/App.xcodeproj/project.pbxproj")
if not project.exists(): raise SystemExit(f"Xcode project not found: {project}")
required = ["IOS_TEAM_ID","IOS_BUNDLE_ID","IOS_CODE_SIGN_IDENTITY","IOS_PROVISIONING_PROFILE_SPECIFIER","IOS_SIGNING_KEYCHAIN","APP_VERSION_NAME","APP_BUILD_NUMBER"]
missing = [name for name in required if not os.environ.get(name)]
if missing: raise SystemExit("Missing Publisher iOS signing variables: " + ", ".join(missing))

entitlements = Path('ios/App/App/App.entitlements')
entitlements.write_text('''<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0">\n<dict>\n  <key>aps-environment</key>\n  <string>production</string>\n</dict>\n</plist>\n''')

def pbx_quote(value: str) -> str: return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'
def set_setting(body: str, key: str, value: str, indent: str) -> str:
    pattern = re.compile(rf"(?m)^(?P<indent>\s*){re.escape(key)}\s*=\s*[^;]*;\s*$")
    body, count = pattern.subn(rf"\g<indent>{key} = {value};", body)
    if count == 0:
        if body and not body.endswith("\n"): body += "\n"
        body += f"{indent}{key} = {value};\n"
    return body

text = project.read_text()
block_pattern = re.compile(r"(?P<head>buildSettings\s*=\s*\{\s*\n?)(?P<body>.*?)(?P<tail>\n?\s*\};)", re.S)
patched = 0

def patch_block(match: re.Match) -> str:
    global patched
    body = match.group("body")
    if "PRODUCT_BUNDLE_IDENTIFIER" not in body: return match.group(0)
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
        "CODE_SIGN_ENTITLEMENTS": "App/App.entitlements",
    }
    for key, value in settings.items(): body = set_setting(body, key, value, indent)
    patched += 1
    return match.group("head") + body + match.group("tail")

text = block_pattern.sub(patch_block, text)
if patched < 2: raise SystemExit(f"Expected to patch at least App Debug/Release configurations, patched {patched}. Found PRODUCT_BUNDLE_IDENTIFIER occurrences: {text.count('PRODUCT_BUNDLE_IDENTIFIER')}")
project.write_text(text)
print(f"Scoped manual App Store signing and push entitlement to the App target in {patched} Xcode configurations.")
